const imageInput = document.getElementById('imageInput');
const preview = document.getElementById('preview');
const previewContainer = document.getElementById('previewContainer');
const submitBtn = document.getElementById('submitBtn');
const output = document.getElementById('output');
const fileSummary = document.getElementById('fileSummary');
const langToggle = document.getElementById('langToggle');
const loading = document.getElementById('loading');
const tabAnalyzer = document.getElementById('tabAnalyzer');
const tabGenerator = document.getElementById('tabGenerator');
const analyzerTab = document.getElementById('analyzerTab');
const generatorTab = document.getElementById('generatorTab');
const generateBtn = document.getElementById('generateBtn');
const generatorOutput = document.getElementById('generatorOutput');
const recordSpeechBtn = document.getElementById('recordSpeechBtn');
const speechStatus = document.getElementById('speechStatus');

// ── E-Prescription structured medicine data ──────────────────────────────────
let medicines = [];       // Array of structured medicine objects
let rxEditingIndex = -1;  // -1 = adding new; ≥0 = editing existing entry
let recognition = null;
let recognizing = false;


document.querySelector('.upload-btn').addEventListener('click', (e) => {
  e.preventDefault();
  imageInput.click();
});


imageInput.addEventListener('change', () => {
  const files = Array.from(imageInput.files);
  previewContainer.innerHTML = '';

  if (!files.length) {
    if (fileSummary) fileSummary.textContent = 'No images selected yet.';
    return;
  }

  if (fileSummary) {
    fileSummary.textContent = `${files.length} image${files.length === 1 ? '' : 's'} ready to scan.`;
  }
  files.forEach((file, index) => {
    const image = index === 0 ? preview : document.createElement('img');
    image.className = 'upload-preview';
    image.alt = `Selected medicine image ${index + 1}`;
    image.hidden = false;
    previewContainer.appendChild(image);

    const reader = new FileReader();
    reader.onload = (event) => { image.src = event.target.result; };
    reader.readAsDataURL(file);
  });
});

const uploadZone = document.querySelector('.upload-btn');
['dragenter', 'dragover'].forEach((eventName) => {
  uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    uploadZone.classList.add('is-dragging');
  });
});
['dragleave', 'drop'].forEach((eventName) => {
  uploadZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    uploadZone.classList.remove('is-dragging');
  });
});
uploadZone.addEventListener('drop', (event) => {
  const files = event.dataTransfer.files;
  if (!files.length) return;
  imageInput.files = files;
  imageInput.dispatchEvent(new Event('change'));
});

// Submit for processing
submitBtn.addEventListener('click', async () => {
  const files = imageInput.files;
  if (!files.length) {
    showError('Please select an image first.');
    return;
  }
  
  submitBtn.disabled = true;
  loading.style.display = 'block';
  output.innerHTML = '';

  const formData = new FormData();
  Array.from(files).forEach(file => formData.append('images', file));
  
  // Add language parameter
  const lang = langToggle.value;
  formData.append('language', lang);

  try {
    const res = await fetch('/process', { method: 'POST', body: formData });
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    }
    
    const data = await res.json();
    loading.style.display = 'none';
    
    if (data.error) {
      showError(data.error);
    } else {
      renderResults(data);
    }
  } catch (err) {
    loading.style.display = 'none';
    showError(`Error: ${err.message}`);
    console.error('Error details:', err);
  } finally {
    submitBtn.disabled = false;
  }
});

function showGeneratorError(message) {
  generatorOutput.innerHTML = `<div class="error" style="background: #fee; color: #c33; padding: 15px; border-radius: 8px; margin: 10px 0;">
    ⚠️ ${message}
  </div>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// MEDICINE FORM: helper to read timing checkboxes
// ─────────────────────────────────────────────────────────────────────────────
function rxGetTiming() {
  return Array.from(document.querySelectorAll('input[name="rxTiming"]:checked'))
              .map(cb => cb.value);
}

// ─────────────────────────────────────────────────────────────────────────────
// MEDICINE FORM: clear all entry fields
// ─────────────────────────────────────────────────────────────────────────────
function clearMedicineForm() {
  document.getElementById('rxMedicineName').value = '';
  document.getElementById('rxDosage').value       = '';
  document.getElementById('rxFrequency').value    = '';
  document.getElementById('rxFood').value         = '';
  document.getElementById('rxDuration').value     = '';
  document.getElementById('rxSpecial').value      = '';
  document.querySelectorAll('input[name="rxTiming"]').forEach(cb => {
    cb.checked  = false;
    cb.disabled = false;
  });
  document.getElementById('rxFormError').textContent = '';
  document.getElementById('rxAddBtn').textContent = '+ Add Medicine';
  rxEditingIndex = -1;
}

// ─────────────────────────────────────────────────────────────────────────────
// MEDICINE FORM: frequency change → disable/enable timing checkboxes
// ─────────────────────────────────────────────────────────────────────────────
document.getElementById('rxFrequency').addEventListener('change', function () {
  const isAsNeeded = this.value === 'As needed';
  document.querySelectorAll('input[name="rxTiming"]').forEach(cb => {
    cb.disabled = isAsNeeded;
    if (isAsNeeded) cb.checked = false;
  });
  const hint = document.getElementById('rxTimingHint');
  const req  = document.getElementById('rxTimingRequired');
  if (isAsNeeded) {
    hint.textContent = 'Timing not applicable for "As needed" frequency.';
    req.style.display = 'none';
  } else {
    hint.textContent = 'Select one or more timing options.';
    req.style.display = '';
  }
});

// ─────────────────────────────────────────────────────────────────────────────
// MEDICINE FORM: render the added-medicines list
// ─────────────────────────────────────────────────────────────────────────────
function renderMedicineList() {
  const listEl   = document.getElementById('rxMedicineList');
  const emptyEl  = document.getElementById('rxEmptyState');
  const countEl  = document.getElementById('rxMedicineCount');
  countEl.textContent = medicines.length;

  if (medicines.length === 0) {
    listEl.innerHTML = '';
    listEl.appendChild(emptyEl);
    emptyEl.style.display = '';
    return;
  }
  emptyEl.style.display = 'none';

  let html = '<table class="rx-table"><thead><tr>'
    + '<th>#</th><th>Medicine</th><th>Dosage</th><th>Frequency</th>'
    + '<th>Timing</th><th>Food</th><th>Duration</th><th>Actions</th>'
    + '</tr></thead><tbody>';

  medicines.forEach((m, i) => {
    const timing  = (m.timing && m.timing.length) ? m.timing.join(', ') : '—';
    const special = m.special_instructions ? `<br><em class="rx-special-note">Note: ${escapeHtml(m.special_instructions)}</em>` : '';
    html += `<tr>
      <td>${i + 1}</td>
      <td>${escapeHtml(m.name)}${special}</td>
      <td>${escapeHtml(m.dosage)}</td>
      <td>${escapeHtml(m.frequency)}</td>
      <td>${escapeHtml(timing)}</td>
      <td>${escapeHtml(m.food_instruction)}</td>
      <td>${escapeHtml(m.duration)}</td>
      <td class="rx-action-cell">
        <button class="rx-edit-btn" onclick="editMedicine(${i})" type="button">Edit</button>
        <button class="rx-remove-btn" onclick="removeMedicine(${i})" type="button">Remove</button>
      </td>
    </tr>`;
  });

  html += '</tbody></table>';
  listEl.innerHTML = html;
}

// ─────────────────────────────────────────────────────────────────────────────
// MEDICINE FORM: add or update a medicine entry
// ─────────────────────────────────────────────────────────────────────────────
function addOrUpdateMedicine() {
  const name      = document.getElementById('rxMedicineName').value.trim();
  const dosage    = document.getElementById('rxDosage').value.trim();
  const frequency = document.getElementById('rxFrequency').value.trim();
  const food      = document.getElementById('rxFood').value.trim();
  const duration  = document.getElementById('rxDuration').value.trim();
  const special   = document.getElementById('rxSpecial').value.trim();
  const timing    = rxGetTiming();
  const errEl     = document.getElementById('rxFormError');

  // ── Validation ──
  if (!name) {
    errEl.textContent = '⚠️ Medicine name is required.';
    document.getElementById('rxMedicineName').focus();
    return;
  }
  if (!dosage) {
    errEl.textContent = '⚠️ Dosage is required.';
    document.getElementById('rxDosage').focus();
    return;
  }
  if (!frequency) {
    errEl.textContent = '⚠️ Please select a frequency.';
    document.getElementById('rxFrequency').focus();
    return;
  }
  if (frequency !== 'As needed' && timing.length === 0) {
    errEl.textContent = '⚠️ Please select at least one timing.';
    return;
  }
  if (!food) {
    errEl.textContent = '⚠️ Please select a food instruction.';
    document.getElementById('rxFood').focus();
    return;
  }
  if (!duration) {
    errEl.textContent = '⚠️ Duration is required.';
    document.getElementById('rxDuration').focus();
    return;
  }
  errEl.textContent = '';

  const entry = { name, dosage, frequency, timing, food_instruction: food, duration, special_instructions: special };

  if (rxEditingIndex >= 0) {
    medicines[rxEditingIndex] = entry;
  } else {
    medicines.push(entry);
  }

  clearMedicineForm();
  renderMedicineList();
}

// ─────────────────────────────────────────────────────────────────────────────
// MEDICINE FORM: edit an existing medicine (loads it back into the form)
// ─────────────────────────────────────────────────────────────────────────────
function editMedicine(index) {
  const m = medicines[index];
  if (!m) return;

  document.getElementById('rxMedicineName').value = m.name;
  document.getElementById('rxDosage').value       = m.dosage;
  document.getElementById('rxFrequency').value    = m.frequency;
  document.getElementById('rxFood').value         = m.food_instruction;
  document.getElementById('rxDuration').value     = m.duration;
  document.getElementById('rxSpecial').value      = m.special_instructions || '';

  // Apply timing checkboxes
  const isAsNeeded = m.frequency === 'As needed';
  document.querySelectorAll('input[name="rxTiming"]').forEach(cb => {
    cb.disabled = isAsNeeded;
    cb.checked  = !isAsNeeded && m.timing.includes(cb.value);
  });

  // Update timing hint
  const hint = document.getElementById('rxTimingHint');
  const req  = document.getElementById('rxTimingRequired');
  if (isAsNeeded) {
    hint.textContent  = 'Timing not applicable for "As needed" frequency.';
    req.style.display = 'none';
  } else {
    hint.textContent  = 'Select one or more timing options.';
    req.style.display = '';
  }

  rxEditingIndex = index;
  document.getElementById('rxAddBtn').textContent = '✔ Update Medicine';
  document.getElementById('rxFormError').textContent = '';
  // Scroll form into view
  document.getElementById('rxEntryPanel').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ─────────────────────────────────────────────────────────────────────────────
// MEDICINE FORM: remove a medicine from the list
// ─────────────────────────────────────────────────────────────────────────────
function removeMedicine(index) {
  // If currently editing the item being removed, reset the form
  if (rxEditingIndex === index) clearMedicineForm();
  else if (rxEditingIndex > index) rxEditingIndex--;  // Adjust index after splice

  medicines.splice(index, 1);
  renderMedicineList();
}

// ─────────────────────────────────────────────────────────────────────────────
// PRESCRIPTION GENERATOR: send structured data to Flask
// ─────────────────────────────────────────────────────────────────────────────
async function generatePrescription() {
  const patientName  = document.getElementById('patientName').value.trim();
  const patientAge   = document.getElementById('patientAge').value.trim();
  const patientGender = document.getElementById('patientGender').value.trim();
  const patientPhone  = document.getElementById('patientPhone').value.trim();

  // Patient field validation (unchanged)
  if (!patientName) { showGeneratorError('Please enter patient name.'); return; }
  if (!patientAge)  { showGeneratorError('Please enter patient age.');  return; }
  if (isNaN(patientAge) || Number(patientAge) < 1 || Number(patientAge) > 150) {
    showGeneratorError('Please enter a valid age (1–150).');
    return;
  }
  if (!patientGender) { showGeneratorError('Please select patient gender.'); return; }
  if (!/^[6-9]\d{9}$/.test(patientPhone)) {
    showGeneratorError('Please enter a valid 10-digit mobile number.');
    return;
  }

  // At least one medicine required
  if (medicines.length === 0) {
    showGeneratorError('Please add at least one medicine before generating the prescription.');
    return;
  }

  generateBtn.disabled = true;
  generateBtn.textContent = 'Generating…';
  generatorOutput.innerHTML = '';

  try {
    const res = await fetch('/generate-prescription', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_name:  patientName,
        age:           patientAge,
        gender:        patientGender,
        phone_number:  patientPhone,
        medicines:     medicines          // structured array – NO "text" field
      })
    });

    const raw = await res.text();
    let data;
    try {
      data = JSON.parse(raw);
    } catch (parseErr) {
      showGeneratorError(`Server returned invalid JSON:\n${raw}`);
      console.error('Invalid JSON from /generate-prescription:', raw);
      return;
    }

    if (!res.ok) {
      showGeneratorError(data.error || `Failed to generate prescription. HTTP ${res.status}`);
      return;
    }
    if (data.error) {
      showGeneratorError(data.error);
      return;
    }

    // Success
    const driveBtnHtml = data.drive_url 
      ? `<a href="${escapeHtml(data.drive_url)}" target="_blank" class="rx-download-link rx-drive-link" style="background:#4285F4; margin-left:10px;">
          ☁️ View on Google Drive
        </a>` 
      : '';

    generatorOutput.innerHTML = `
      <div class="medicine-card">
        <h3>✅ Prescription Generated</h3>
        <p><b>Patient:</b> ${escapeHtml(data.patient)}</p>
        <p><b>Mobile:</b>  ${escapeHtml(data.phone_number)}</p>
        <p><b>Age:</b>     ${escapeHtml(data.age)}</p>
        <p><b>Gender:</b>  ${escapeHtml(data.gender)}</p>
        <p><b>Medicines:</b> ${data.medicines ? data.medicines.length : medicines.length}</p>
        <br>
        <div class="rx-download-buttons">
          <a href="${escapeHtml(data.download_url || data.local_download_url)}" target="_blank" class="rx-download-link">
            📄 Download Prescription PDF
          </a>
          ${driveBtnHtml}
        </div>
      </div>
    `;

  } catch (err) {
    showGeneratorError(err.message);
  } finally {
    generateBtn.disabled = false;
    generateBtn.textContent = 'Generate Prescription PDF';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// TAB SWITCHING (unchanged)
// ─────────────────────────────────────────────────────────────────────────────
// ─────────────────────────────────────────────────────────────────────────────
// DASHBOARD NAVIGATION
// ─────────────────────────────────────────────────────────────────────────────
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const sections = document.querySelectorAll('.page-section');
  const sectionTargets = document.querySelectorAll('[data-section-target]');

  function showSection(sectionId) {
    // Hide all sections
    sections.forEach(sec => sec.classList.remove('active-section'));
    // Deactivate all nav items
    navItems.forEach(nav => nav.classList.remove('active'));

    // Show target section
    const targetSec = document.getElementById(sectionId);
    if (targetSec) targetSec.classList.add('active-section');

    // Activate corresponding nav item
    const targetNav = document.querySelector(`.nav-item[data-section="${sectionId}"]`);
    if (targetNav) targetNav.classList.add('active');
    
    // Special case for Generator tab which is hidden in the new UI but might be triggered
    if (sectionId === 'generatorTab') {
      const genNav = document.getElementById('tabGenerator');
      if (genNav) genNav.classList.add('active');
    }
  }

  // Bind sidebar nav items
  navItems.forEach(nav => {
    nav.addEventListener('click', () => {
      const targetId = nav.getAttribute('data-section');
      if (targetId) showSection(targetId);
    });
  });

  // Bind quick action buttons
  sectionTargets.forEach(btn => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-section-target');
      if (targetId) showSection(targetId);
    });
  });

  // Legacy tab overrides (if old buttons are still clicked)
  if (tabAnalyzer) tabAnalyzer.addEventListener('click', () => showSection('scanSection'));
  if (tabGenerator) tabGenerator.addEventListener('click', () => showSection('generatorTab'));
}

generateBtn.addEventListener('click', generatePrescription);
document.getElementById('rxAddBtn').addEventListener('click', addOrUpdateMedicine);
recordSpeechBtn.addEventListener('click', toggleSpeechRecognition);

initNavigation();

function showError(message) {
  output.innerHTML = `<div class="error" style="background: #fee; color: #c33; padding: 15px; border-radius: 8px; margin: 10px 0;">
    ⚠️ ${message}
  </div>`;
}

function initializeSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    speechStatus.textContent = 'Speech recognition is not supported in this browser. Please use Chrome or Edge.';
    recordSpeechBtn.disabled = true;
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    recognizing = true;
    speechStatus.textContent = '🎤 Listening... speak clearly into your microphone.';
    recordSpeechBtn.textContent = '⏹️ Stop Recording';
  };

  recognition.onresult = (event) => {
    const transcript = Array.from(event.results)
      .map(result => result[0].transcript)
      .join(' ');

    if (transcript) {
      // Append dictated text to the medicine name field (replaces old textarea target)
      const nameField = document.getElementById('rxMedicineName');
      if (nameField) {
        nameField.value = (nameField.value ? nameField.value + ' ' : '') + transcript.trim();
      }
      speechStatus.textContent = '✅ Medicine name captured. Click "Stop" to finish.';
    }
  };

  recognition.onerror = (event) => {
    speechStatus.textContent = `❌ Speech recognition error: ${event.error}`;
  };

  recognition.onend = () => {
    recognizing = false;
    recordSpeechBtn.textContent = '🎙️ Dictate Name';
    if (!speechStatus.textContent.includes('captured')) {
      speechStatus.textContent = '🛑 Recording stopped. Press the button again to try again.';
    }
  };
}

function toggleSpeechRecognition() {
  if (!recognition) {
    initializeSpeechRecognition();
    if (!recognition) return;
  }

  if (recognizing) {
    recognition.stop();
    return;
  }

  try {
    recognition.start();
  } catch (err) {
    speechStatus.textContent = `❌ Could not start speech recognition: ${err.message}`;
  }
}

function renderResults(results) {
  if (!Array.isArray(results) || !results.length) {
    showError('No results found. Please try another image.');
    return;
  }

  const lang = langToggle.value;
  const labels = {
    uses: lang === 'kn' ? 'ಉಪಯೋಗಗಳು (Uses)' : '💊 Uses',
    sideEffects: lang === 'kn' ? 'ಅಡ್ಡ ಪರಿಣಾಮಗಳು (Side Effects)' : '⚠️ Side Effects',
    expiry: lang === 'kn' ? 'ಮುಕ್ತಾಯ ದಿನಾಂಕ' : '📅 Expiry Date',
    alternates: lang === 'kn' ? 'ಪರ್ಯಾಯ ಔಷಧಗಳು' : '🔄 Alternative Medicines',
    source: lang === 'kn' ? 'ಮಾಹಿತಿ ಮೂಲ' : '📊 Data Source'
  };

  let html = '';

  results.forEach((r, index) => {
    // Handle response from backend
    const medicineName =
      r.medicine_name ||
      r.generic_name ||
      r.brand_name ||
      r.extracted_name ||
      'Unknown Medicine';

    const brandName =
      r.brand_name || 'Information not available';

    const genericName =
      r.generic_name || 'Information not available';

    const strength =
      r.strength || 'Information not available';

    const dosageForm =
      r.dosage_form || 'Information not available';

    const expiryDate =
      r.expiry_date || r.expiry || 'NOT FOUND';

    const source =
      r.source || 'Gemini';

    // Get uses
    let uses = r.uses || r.uses_summary || [];
    if (typeof uses === 'string') {
      uses = [uses];
    }

    // Get side effects
    let sideEffects =
      r.side_effects || r.side_effects_summary || [];

    if (typeof sideEffects === 'string') {
      sideEffects = [sideEffects];
    }

    // Get alternatives
    let alternatives =
      r.alternatives || r.alternates || [];

    if (typeof alternatives === 'string') {
      alternatives = [alternatives];
    }

    html += `
      <div class="medicine-card" style="background: white; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">

        <div style="border-bottom: 2px solid #4CAF50; padding-bottom: 10px; margin-bottom: 15px;">

          <div class="result-name"
              style="font-size: 24px; font-weight: bold; color: #2c3e50;">
            ${escapeHtml(medicineName)}
          </div>

          <div class="result-brand"
              style="font-size: 16px; color: #444; margin-top: 6px;">
            Brand: ${escapeHtml(brandName)}
          </div>

          <div style="font-size: 14px; color: #555; margin-top: 5px;">
            Generic: ${escapeHtml(genericName)}
          </div>

          <div style="font-size: 14px; color: #555; margin-top: 5px;">
            Strength: ${escapeHtml(strength)}
          </div>

          <div style="font-size: 14px; color: #555; margin-top: 5px;">
            Dosage Form: ${escapeHtml(dosageForm)}
          </div>

          <div class="result-expiry"
              style="color: #666; margin-top: 5px;">
            ${labels.expiry}: ${escapeHtml(expiryDate)}
          </div>

          <div style="font-size: 12px; color: #999; margin-top: 5px;">
            ${labels.source}: ${escapeHtml(source)}
          </div>

        </div>

        ${formatSection(labels.uses, uses, 'uses')}

        ${formatSection(labels.sideEffects, sideEffects, 'side-effects')}

        ${formatSection(labels.alternates, alternatives, 'alternatives')}

        ${(uses.length === 0 ||
          (uses.length === 1 &&
          uses[0].includes('No FDA information'))) ? `
          <div style="background: #fff3cd; padding: 12px; border-radius: 8px; margin-top: 15px;">
            <strong>ℹ️ Note:</strong>
            This information is not available in the FDA database.
            Please consult a healthcare provider.
          </div>
        ` : ''}

      </div>
    `;
  });

  output.innerHTML = html;
}

function formatSection(title, items, sectionClass) {
  if (!items || items.length === 0) {
    return '';
  }
  
  // Clean and filter items
  const cleanItems = [];
  
  items.forEach(item => {
    if (typeof item !== 'string') return;
    
    // Skip boilerplate text
    const skipPatterns = [
      'see full prescribing',
      'manufactured by',
      'distributed by',
      'package insert',
      'store at',
      'dispense in',
      'www.',
      'contact',
      'inc.',
      'lupin pharmaceuticals',
      'adverse reactions',
      'indications and usage'
    ];
    
    let text = item.trim();
    
    // Skip if matches any skip pattern
    if (skipPatterns.some(pattern => text.toLowerCase().includes(pattern))) {
      return;
    }
    
    // Remove numbering like "1)", "2)", "o", etc.
    text = text.replace(/^\d+\)?\s*/, '');
    text = text.replace(/^[oO]\s*/, '');
    text = text.replace(/^[•\-*]\s*/, '');
    
    // Skip if too short or too long
     // Allow shorter but meaningful items (min length 5) so we can show up to 5 uses/side-effects
     if (sectionClass !== 'alternatives' && (text.length < 5 || text.length > 300)) {
    return;
}
    
    // Skip if it's just a number
    if (/^\d+$/.test(text)) {
      return;
    }
    
    // Capitalize first letter
    text = text.charAt(0).toUpperCase() + text.slice(1);
    
    // Ensure it ends with proper punctuation
    if (!text.match(/[.!?]$/)) {
      text += '.';
    }
    
    cleanItems.push(text);
  });
  
  // Remove duplicates
  const uniqueItems = [...new Set(cleanItems)];
  
  if (uniqueItems.length === 0) {
    return '';
  }
  
  // Limit to 5 items per section
  const limitedItems = uniqueItems.slice(0, 5);
  
  return `
    <div class="section" style="margin-top: 20px;">
      <div class="section-title" style="font-weight: bold; font-size: 18px; margin-bottom: 10px; color: #2c3e50;">${title}</div>
      <div class="full-text" style="background: #f9f9f9; padding: 12px; border-radius: 8px;">
        <ul style="margin: 0; padding-left: 20px;">
          ${limitedItems.map(item => `<li style="margin-bottom: 8px; line-height: 1.5;">${escapeHtml(item)}</li>`).join('')}
        </ul>
      </div>
    </div>
  `;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Add loading indicator styles if not already present
if (!document.querySelector('#loading-style')) {
  const style = document.createElement('style');
  style.id = 'loading-style';
  style.textContent = `
    #loading {
      display: none;
      text-align: center;
      padding: 20px;
      margin: 20px 0;
    }
    
    .spinner {
      border: 3px solid #f3f3f3;
      border-top: 3px solid #4CAF50;
      border-radius: 50%;
      width: 40px;
      height: 40px;
      animation: spin 1s linear infinite;
      margin: 0 auto;
    }
    
    @keyframes spin {
      0% { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    
    .error {
      background: #fee;
      color: #c33;
      padding: 15px;
      border-radius: 8px;
      margin: 10px 0;
      border-left: 4px solid #c33;
    }
    
    .medicine-card {
      animation: fadeIn 0.3s ease-in;
    }
    
    @keyframes fadeIn {
      from {
        opacity: 0;
        transform: translateY(10px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
  `;
  document.head.appendChild(style);
}