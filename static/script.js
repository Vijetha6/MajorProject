const imageInput = document.getElementById('imageInput');
const preview = document.getElementById('preview');
const previewContainer = document.getElementById('previewContainer');
const submitBtn = document.getElementById('submitBtn');
const output = document.getElementById('output');
const fileSummary = document.getElementById('fileSummary');
const langToggle = document.getElementById('langToggle');
const loading = document.getElementById('loading');
const generateBtn = document.getElementById('generateBtn');
const generatorOutput = document.getElementById('generatorOutput');
const recordSpeechBtn = document.getElementById('recordSpeechBtn');
const speechStatus = document.getElementById('speechStatus');
let selectedPatient = null;
let selectedPatientVisits = [];

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
// PRESCRIPTION GENERATOR: save reviewed voice-to-text content to Flask
// ─────────────────────────────────────────────────────────────────────────────
function prescriptionInput() {
  const prescriptionText = document.getElementById('prescriptionText').value.trim();
  if (!prescriptionText) throw new Error('Record a prescription before saving.');
  return { text: prescriptionText };
}

const prescriptionTextField = document.getElementById('prescriptionText');
if (prescriptionTextField) {
  prescriptionTextField.addEventListener('input', () => {
    generateBtn.disabled = !prescriptionTextField.value.trim();
  });
}

async function generatePrescription() {
  generatorOutput.innerHTML = '';
  try {
    if (!selectedPatient) throw new Error('Select a patient before saving a prescription.');
    const prescription = prescriptionInput();
    generateBtn.disabled = true;
    generateBtn.textContent = 'Saving visit…';
    const payload = {
      patient_id: selectedPatient.patient_id,
      ...prescription
    };
    const response = await fetch('/generate-prescription', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Failed to save prescription (HTTP ${response.status}).`);

    const driveLink = data.drive_url
      ? `<a href="${escapeHtml(data.drive_url)}" target="_blank" rel="noopener" class="rx-download-link rx-drive-link">View on Google Drive</a>`
      : '';
    generatorOutput.innerHTML = `
      <div class="medicine-card">
        <h3>Visit saved and prescription generated</h3>
        <p><b>Patient:</b> ${escapeHtml(data.patient)} · ${escapeHtml(data.patient_id)}</p>
        <p><b>Visit ID:</b> ${escapeHtml(data.visit_id)}</p>
        <p><b>Doctor ID:</b> ${escapeHtml(data.doctor_id)}</p>
        <p><b>Medicines:</b> ${data.medicines.length}</p>
        <div class="rx-download-buttons">
          <a href="${escapeHtml(data.download_url)}" target="_blank" rel="noopener" class="rx-download-link">Download prescription PDF</a>
          ${driveLink}
        </div>
      </div>`;
    generateBtn.textContent = 'Visit saved';
    generateBtn.disabled = true;
    recordSpeechBtn.disabled = true;
    await loadSelectedPatient(selectedPatient.patient_id, false);
  } catch (error) {
    showGeneratorError(error.message);
    generateBtn.disabled = !document.getElementById('prescriptionText').value.trim();
    generateBtn.textContent = 'Save visit and generate PDF';
  }
}

if (generateBtn) generateBtn.addEventListener('click', generatePrescription);

async function doctorJsonRequest(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error || `Request failed (HTTP ${response.status}).`);
    error.data = data;
    throw error;
  }
  return data;
}

function renderPatientSearchResults(patients) {
  const results = document.getElementById('patientSearchResults');
  results.innerHTML = '';
  if (!patients.length) {
    results.innerHTML = '<p class="empty-state">No matching patient was found. Register a new patient below.</p>';
    return;
  }
  patients.forEach(patient => {
    const card = document.createElement('article');
    card.className = 'patient-search-result';
    const summary = document.createElement('p');
    summary.textContent = `${patient.patient_name} · ${patient.patient_id} · ${patient.mobile_number}`;
    const selectButton = document.createElement('button');
    selectButton.type = 'button';
    selectButton.className = 'secondary-button';
    selectButton.textContent = 'Select patient and view history';
    selectButton.addEventListener('click', () => loadSelectedPatient(patient.patient_id));
    card.append(summary, selectButton);
    results.appendChild(card);
  });
}

async function searchDoctorPatients(searchBy, value) {
  const status = document.getElementById('patientSearchStatus');
  const registration = document.getElementById('newPatientRegistration');
  selectedPatient = null;
  selectedPatientVisits = [];
  document.getElementById('selectedPatientPanel').hidden = true;
  document.getElementById('prescriptionWorkflow').hidden = true;
  status.textContent = 'Searching patient records…';
  registration.hidden = true;
  document.getElementById('patientSearchResults').innerHTML = '';
  try {
    const query = new URLSearchParams({ [searchBy]: value });
    const data = await doctorJsonRequest(`/doctor/patients/search?${query}`);
    renderPatientSearchResults(data.patients || []);
    if (!data.patients || data.patients.length === 0) {
      status.textContent = 'No match found. Register the patient if they are new.';
      registration.hidden = false;
      if (searchBy === 'mobile_number') {
        document.getElementById('newPatientMobile').value = value;
      }
    } else {
      status.textContent = `${data.patients.length} matching patient record(s). Select the correct patient.`;
    }
  } catch (error) {
    status.textContent = error.message;
  }
}

function renderPatientHistory(visits) {
  const historyList = document.getElementById('patientHistoryList');
  if (!visits.length) {
    historyList.innerHTML = '<p class="empty-state">This patient has no previous prescriptions.</p>';
    return;
  }

  historyList.innerHTML = visits.map(visit => {
    const medicinesHtml = visit.medicines.length
      ? `<ul class="visit-medicine-list">${visit.medicines.map(medicine => `
          <li><strong>${escapeHtml(medicine.medicine_name)}</strong> — ${escapeHtml(medicine.dosage)}
            <span>Frequency: ${escapeHtml(medicine.frequency || 'Not specified')}</span>
            <span>Duration: ${escapeHtml(medicine.duration || 'Not specified')}</span>
            <span>Instructions: ${escapeHtml(medicine.instructions || medicine.special_instructions || medicine.food_instruction || 'None')}</span>
          </li>`).join('')}</ul>`
      : '<p>No medicines were recorded for this visit.</p>';
    return `<article class="visit-history-card">
      <div class="visit-history-heading">
        <div><h4>${escapeHtml(visit.visit_date)} · ${escapeHtml(visit.visit_id)}</h4><p>Doctor ID: ${escapeHtml(visit.doctor_id)}</p></div>
        <a class="secondary-button" href="${escapeHtml(visit.pdf_url)}" target="_blank" rel="noopener">View prescription PDF</a>
      </div>
      ${visit.diagnosis ? `<p><strong>Diagnosis:</strong> ${escapeHtml(visit.diagnosis)}</p>` : ''}
      ${visit.notes ? `<p><strong>Prescription text / notes:</strong> ${escapeHtml(visit.notes)}</p>` : ''}
      ${medicinesHtml}
    </article>`;
  }).join('');
}

async function loadSelectedPatient(patientId, startNew = false) {
  const status = document.getElementById('patientSearchStatus');
  status.textContent = 'Loading patient history…';
  try {
    const data = await doctorJsonRequest(
      `/doctor/patients/${encodeURIComponent(patientId)}/history`
    );
    selectedPatient = data.patient;
    selectedPatientVisits = data.visits || [];
    document.getElementById('selectedPatientName').textContent = selectedPatient.patient_name;
    document.getElementById('selectedPatientId').textContent = selectedPatient.patient_id;
    document.getElementById('selectedPatientMobile').textContent = selectedPatient.mobile_number;
    document.getElementById('selectedPatientAge').textContent = `${selectedPatient.age} years`;
    document.getElementById('selectedPatientGender').textContent = selectedPatient.gender;
    document.getElementById('selectedPatientVisitCount').textContent = selectedPatientVisits.length;
    document.getElementById('updatedPatientMobile').value = selectedPatient.mobile_number;
    document.getElementById('selectedPatientPanel').hidden = false;
    document.getElementById('newPatientRegistration').hidden = true;
    const hasHistory = selectedPatientVisits.length > 0;
    const historyPanel = document.getElementById('patientHistoryPanel');
    const historyButton = document.getElementById('viewPatientHistoryBtn');
    const newPrescriptionButton = document.getElementById('startPrescriptionBtn');
    historyPanel.hidden = !hasHistory;
    historyButton.hidden = !hasHistory;
    historyButton.textContent = 'Hide previous prescriptions';
    newPrescriptionButton.hidden = !hasHistory;
    document.getElementById('patientSearchResults').innerHTML = '';
    document.getElementById('patientSearchStatus').textContent = '';
    renderPatientHistory(selectedPatientVisits);
    if (startNew || !hasHistory) beginNewPrescription();
  } catch (error) {
    status.textContent = error.message;
  }
}

function beginNewPrescription() {
  if (!selectedPatient) return;
  prescriptionTextField.value = '';
  prescriptionTextField.dispatchEvent(new Event('input'));
  speechStatus.textContent = '';
  document.getElementById('prescriptionPatientSummary').textContent =
    `${selectedPatient.patient_name} · ${selectedPatient.patient_id} · ${selectedPatient.mobile_number}`;
  document.getElementById('prescriptionWorkflow').hidden = false;
  document.getElementById('generatorOutput').innerHTML = '';
  generateBtn.textContent = 'Save visit and generate PDF';
  generateBtn.disabled = true;
  recordSpeechBtn.disabled = false;
  document.getElementById('prescriptionWorkflow').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

const patientIdSearchForm = document.getElementById('patientIdSearchForm');
if (patientIdSearchForm) {
  patientIdSearchForm.addEventListener('submit', event => {
    event.preventDefault();
    const value = document.getElementById('patientIdSearch').value.trim();
    if (!value) {
      document.getElementById('patientSearchStatus').textContent = 'Enter a Patient ID.';
      return;
    }
    searchDoctorPatients('patient_id', value);
  });
}

const patientMobileSearchForm = document.getElementById('patientMobileSearchForm');
if (patientMobileSearchForm) {
  patientMobileSearchForm.addEventListener('submit', event => {
    event.preventDefault();
    const value = document.getElementById('patientMobileSearch').value.trim();
    if (!value) {
      document.getElementById('patientSearchStatus').textContent = 'Enter a mobile number.';
      return;
    }
    searchDoctorPatients('mobile_number', value);
  });
}

const registerPatientForm = document.getElementById('registerPatientForm');
if (registerPatientForm) {
  registerPatientForm.addEventListener('submit', async event => {
    event.preventDefault();
    const status = document.getElementById('registerPatientStatus');
    status.textContent = 'Registering patient…';
    const payload = Object.fromEntries(new FormData(registerPatientForm).entries());
    try {
      const data = await doctorJsonRequest('/doctor/patients', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      status.textContent = 'Patient registered.';
      await loadSelectedPatient(data.patient.patient_id, true);
    } catch (error) {
      status.textContent = error.message;
      if (error.data && error.data.existing_patients) {
        renderPatientSearchResults(error.data.existing_patients);
      }
    }
  });
}

const updatePatientMobileBtn = document.getElementById('updatePatientMobileBtn');
if (updatePatientMobileBtn) {
  updatePatientMobileBtn.addEventListener('click', async () => {
    if (!selectedPatient) return;
    const status = document.getElementById('updatePatientMobileStatus');
    status.textContent = 'Updating…';
    try {
      const data = await doctorJsonRequest(
        `/doctor/patients/${encodeURIComponent(selectedPatient.patient_id)}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            mobile_number: document.getElementById('updatedPatientMobile').value.trim()
          })
        }
      );
      selectedPatient = data.patient;
      document.getElementById('selectedPatientMobile').textContent = selectedPatient.mobile_number;
      document.getElementById('updatedPatientMobile').value = selectedPatient.mobile_number;
      document.getElementById('prescriptionPatientSummary').textContent =
        `${selectedPatient.patient_name} · ${selectedPatient.patient_id} · ${selectedPatient.mobile_number}`;
      status.textContent = 'Mobile number updated. Patient history remains linked by Patient ID.';
    } catch (error) {
      status.textContent = error.message;
    }
  });
}

const viewPatientHistoryBtn = document.getElementById('viewPatientHistoryBtn');
if (viewPatientHistoryBtn) {
  viewPatientHistoryBtn.addEventListener('click', () => {
    const panel = document.getElementById('patientHistoryPanel');
    panel.hidden = !panel.hidden;
    viewPatientHistoryBtn.textContent = panel.hidden
      ? 'View previous prescriptions'
      : 'Hide previous prescriptions';
  });
}

const startPrescriptionBtn = document.getElementById('startPrescriptionBtn');
if (startPrescriptionBtn) startPrescriptionBtn.addEventListener('click', beginNewPrescription);
const closePrescriptionBtn = document.getElementById('closePrescriptionBtn');
if (closePrescriptionBtn) closePrescriptionBtn.addEventListener('click', () => {
  document.getElementById('prescriptionWorkflow').hidden = true;
});
const clearSelectedPatientBtn = document.getElementById('clearSelectedPatientBtn');
if (clearSelectedPatientBtn) clearSelectedPatientBtn.addEventListener('click', () => {
  selectedPatient = null;
  selectedPatientVisits = [];
  document.getElementById('selectedPatientPanel').hidden = true;
  document.getElementById('prescriptionWorkflow').hidden = true;
});

if (recordSpeechBtn) recordSpeechBtn.addEventListener('click', toggleSpeechRecognition);

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
      // Append speech recognition output to the prescription transcript.
      const prescriptionField = document.getElementById('prescriptionText');

      if (prescriptionField) {
          prescriptionField.value +=
              (prescriptionField.value ? '\n' : '') + transcript.trim();
          prescriptionField.dispatchEvent(new Event('input'));
      }

      speechStatus.textContent = '✅ Speech captured successfully.';
    }
  };

  recognition.onerror = (event) => {
    speechStatus.textContent = `❌ Speech recognition error: ${event.error}`;
  };

  recognition.onend = () => {
    recognizing = false;
    recordSpeechBtn.textContent = 'Record Prescription';
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
    sameIngredient: lang === 'kn' ? 'ಒಂದೇ ಸಕ್ರಿಯ ಘಟಕಾಂಶದ ಬ್ರ್ಯಾಂಡ್ ಸಲಹೆಗಳು' : '🔄 Same-Ingredient Brand Suggestions',
    otherDrugs: lang === 'kn' ? 'ವೈದ್ಯರು ಪರಿಗಣಿಸಬಹುದಾದ ಇತರ ಔಷಧಿಗಳು' : '💊 Other Drugs a Doctor May Consider',
    source: lang === 'kn' ? 'ಮಾಹಿತಿ ಮೂಲ' : '📊 Data Source',
    brand: lang === 'kn' ? 'ಬ್ರ್ಯಾಂಡ್' : 'Brand',
    generic: lang === 'kn' ? 'ಜನರಿಕ್ ಹೆಸರು' : 'Generic name',
    strength: lang === 'kn' ? 'ಶಕ್ತಿ' : 'Strength',
    dosageForm: lang === 'kn' ? 'ಔಷಧ ರೂಪ' : 'Dosage form',
    reason: lang === 'kn' ? 'ಕಾರಣ' : 'Reason',
    noSuggestions: lang === 'kn' ? 'ವಿಶ್ವಾಸಾರ್ಹ ಸಲಹೆಗಳು ಲಭ್ಯವಿಲ್ಲ.' : 'No reliable suggestions available.',
    suggestionsDisclaimer: lang === 'kn'
      ? 'AI ಮೂಲಕ ರಚಿಸಲಾದ ಔಷಧ ಸಲಹೆಗಳು ಪರಿಶೀಲಿತ ಬದಲಿಗಳು ಅಲ್ಲ. ಯಾವುದೇ ಔಷಧವನ್ನು ಬದಲಿಸುವ ಅಥವಾ ಬದಲಾಗಿ ಬಳಸುವ ಮೊದಲು ಅರ್ಹ ವೈದ್ಯರು ಅಥವಾ ಔಷಧ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ.'
      : 'AI-generated medicine suggestions are not verified substitutes. Always consult a qualified doctor or pharmacist before changing or replacing any medicine.'
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
      formatExpiryDisplay(r.expiry_date || r.expiry || 'NOT FOUND');

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

        ${formatSection(labels.sameIngredient, r.same_ingredient_alternatives, 'same-ingredient-alternatives', labels.noSuggestions, labels)}

        ${formatSection(labels.otherDrugs, r.other_drug_options, 'other-drug-options', labels.noSuggestions, labels)}

        <p class="suggestions-disclaimer" style="margin-top: 16px; padding: 12px; border-left: 4px solid #d6a94f; background: #fff8e6; color: #5f5133; border-radius: 6px;">
          ${escapeHtml(labels.suggestionsDisclaimer)}
        </p>

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

function formatSection(title, items, sectionClass, emptyMessage, labels) {
  if (sectionClass === 'same-ingredient-alternatives' || sectionClass === 'other-drug-options') {
    const suggestions = Array.isArray(items) ? items : [];
    const seen = new Set();
    const availableText = (value) => {
      if (typeof value !== 'string' || !value.trim()) return '';
      const text = value.trim();
      return ['information not available', 'not available', 'unknown', 'n/a', 'na']
        .includes(text.toLowerCase()) ? '' : text;
    };

    const suggestionItems = suggestions.map((item) => {
      if (!item || typeof item !== 'object' || Array.isArray(item)) return '';

      if (sectionClass === 'same-ingredient-alternatives') {
        const brand = availableText(item.brand_name);
        const brandKey = brand.toLowerCase().replace(/[^a-z0-9]/g, '');
        if (!brand || !brandKey || seen.has(brandKey)) return '';
        seen.add(brandKey);

        const details = [
          [labels.generic, availableText(item.generic_name)],
          [labels.strength, availableText(item.strength)],
          [labels.dosageForm, availableText(item.dosage_form)]
        ].filter(([, value]) => value);

        return `<li style="margin-bottom: 10px; line-height: 1.5;">
          <strong>${escapeHtml(labels.brand)}: ${escapeHtml(brand)}</strong>
          ${details.map(([label, value]) => `<div>${escapeHtml(label)}: ${escapeHtml(value)}</div>`).join('')}
        </li>`;
      }

      const medicineName = availableText(item.medicine_name);
      const medicineKey = medicineName.toLowerCase().replace(/[^a-z0-9]/g, '');
      if (!medicineName || !medicineKey || seen.has(medicineKey)) return '';
      seen.add(medicineKey);
      const reason = availableText(item.reason);
      return `<li style="margin-bottom: 10px; line-height: 1.5;">
        <strong>${escapeHtml(medicineName)}</strong>
        ${reason ? `<div>${escapeHtml(labels.reason)}: ${escapeHtml(reason)}</div>` : ''}
      </li>`;
    }).filter(Boolean).slice(0, 5);

    return `
      <div class="section ${sectionClass}" style="margin-top: 20px;">
        <div class="section-title" style="font-weight: bold; font-size: 18px; margin-bottom: 10px; color: #2c3e50;">${escapeHtml(title)}</div>
        <div class="full-text" style="background: #f9f9f9; padding: 12px; border-radius: 8px;">
          ${suggestionItems.length
            ? `<ul style="margin: 0; padding-left: 20px;">${suggestionItems.join('')}</ul>`
            : `<p style="margin: 0;">${escapeHtml(emptyMessage)}</p>`}
        </div>
      </div>
    `;
  }

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
    if ((sectionClass === 'uses' || sectionClass === 'side-effects') && (text.length < 5 || text.length > 300)) {
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

// Keep all page navigation on one delegated click handler.
const pageSections = Array.from(document.querySelectorAll('.page-section'));
const navigationItems = Array.from(document.querySelectorAll('.nav-item'));

function showPageSection(sectionId) {
  const section = document.getElementById(sectionId);
  if (!section || !section.classList.contains('page-section')) {
    console.error(`Navigation target "${sectionId}" is not a page section.`);
    return false;
  }

  pageSections.forEach(pageSection => {
    pageSection.classList.toggle('active-section', pageSection === section);
  });

  navigationItems.forEach(item => {
    item.classList.toggle('active', item.dataset.section === sectionId);
  });

  section.scrollIntoView({ behavior: 'smooth', block: 'start' });
  return true;
}

const initialSection = document.documentElement.dataset.initialSection;
if (initialSection) showPageSection(initialSection);

if (document.documentElement.dataset.navigationInitialized !== 'true') {
  document.documentElement.dataset.navigationInitialized = 'true';
  document.addEventListener('click', event => {
    const clickedElement = event.target instanceof Element
      ? event.target.closest('.nav-item[data-section], [data-section-target]')
      : null;
    if (!clickedElement) return;

    const sectionId = clickedElement.dataset.sectionTarget || clickedElement.dataset.section;
    if (!sectionId || !showPageSection(sectionId)) return;

    if (sectionId === 'inventorySection') {
      loadInventory().catch(error => console.error('Could not load inventory:', error));
    } else if (sectionId === 'alertsSection') {
      loadStaffAlerts().catch(error => console.error('Could not load expiry alerts:', error));
    } else if (sectionId === 'inventorySalesSection') {
      loadSellMedicines().catch(error => console.error('Could not load medicines for sale:', error));
    } else if (sectionId === 'salesHistorySection') {
      loadSalesHistory().catch(error => console.error('Could not load sales history:', error));
    }
  });
}

const staffUpdateImageInput = document.getElementById('staffUpdateImageInput');
const staffUpdateScanBtn = document.getElementById('staffUpdateScanBtn');
const staffUpdateStatus = document.getElementById('staffUpdateStatus');
const staffLocationImageInput = document.getElementById('staffLocationImageInput');
const staffLocationScanBtn = document.getElementById('staffLocationScanBtn');
const staffLocationStatus = document.getElementById('staffLocationStatus');
const staffLocationResult = document.getElementById('staffLocationResult');
const staffLocationSearchInput = document.getElementById('staffLocationSearchInput');
const staffLocationSearchBtn = document.getElementById('staffLocationSearchBtn');
const addMedicineForm = document.getElementById('addMedicineForm');
const editExtractedFieldsBtn = document.getElementById('editExtractedFieldsBtn');
const inventoryTableBody = document.getElementById('inventoryTableBody');
const inventoryRefreshBtn = document.getElementById('inventoryRefreshBtn');
const expiringList = document.getElementById('expiringList');
const expiredList = document.getElementById('expiredList');
const staffLowStockList = document.getElementById('staffLowStockList');
const expiredMedicineModal = document.getElementById('expiredMedicineModal');
const expiredMedicineModalList = document.getElementById('expiredMedicineModalList');
const expiredMedicineWarning = document.getElementById('expiredMedicineWarning');
const closeExpiredMedicineModal = document.getElementById('closeExpiredMedicineModal');
const expiryVerificationNotice = document.getElementById('expiryVerificationNotice');
let pendingOcrExpiry = null;
let expiredMedicinePopupShown = false;

function expiryDaysInMonth(year, month) {
  if (month === 2) {
    return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0) ? 29 : 28;
  }
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

function expiryUtcTimestamp(year, month, day) {
  const timestamp = new Date(0);
  timestamp.setUTCFullYear(year, month - 1, day);
  return timestamp.getTime();
}

function formatExpiryForInput(value) {
  if (!value || value === 'NOT FOUND' || value === 'Information not available') return '';
  const text = String(value).trim();
  const monthNames = {
    jan: 1, january: 1, feb: 2, february: 2, mar: 3, march: 3,
    apr: 4, april: 4, may: 5, jun: 6, june: 6, jul: 7, july: 7,
    aug: 8, august: 8, sep: 9, sept: 9, september: 9, oct: 10,
    october: 10, nov: 11, november: 11, dec: 12, december: 12
  };
  const makeIso = (year, month, day) => {
    if (year < 1 || year > 9999 || month < 1 || month > 12 ||
        day < 1 || day > expiryDaysInMonth(year, month)) return '';
    return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
  };
  const monthEnd = (year, month) => makeIso(year, month, expiryDaysInMonth(year, month));

  let match = text.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (match) return makeIso(Number(match[1]), Number(match[2]), Number(match[3]));

  match = text.match(/^(\d{4})-(\d{1,2})$/);
  if (match) return monthEnd(Number(match[1]), Number(match[2]));

  match = text.match(/^(\d{1,2})\/(\d{4})$/);
  if (match) return monthEnd(Number(match[2]), Number(match[1]));

  match = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (match) return makeIso(Number(match[3]), Number(match[2]), Number(match[1]));

  match = text.match(/^([A-Za-z]{3,9})\.?[\s-]+(\d{4})$/);
  if (match) {
    const month = monthNames[match[1].toLowerCase()];
    return month ? monthEnd(Number(match[2]), month) : '';
  }
  return '';
}

function formatExpiryDisplay(value) {
  const isoDate = formatExpiryForInput(value);
  if (!isoDate) return String(value || '');
  const [year, month, day] = isoDate.split('-').map(Number);
  const lastDay = expiryDaysInMonth(year, month);
  if (day === lastDay) return `${String(month).padStart(2, '0')}/${year}`;
  return `${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}/${year}`;
}

function expiryPresentation(value) {
  const isoDate = formatExpiryForInput(value);
  const display = formatExpiryDisplay(value);
  if (!isoDate) return { display, status: null, label: '' };

  const [year, month, day] = isoDate.split('-').map(Number);
  const todayParts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(new Date()).reduce((parts, item) => {
    if (item.type !== 'literal') parts[item.type] = Number(item.value);
    return parts;
  }, {});
  const remainingDays = (expiryUtcTimestamp(year, month, day) -
    expiryUtcTimestamp(todayParts.year, todayParts.month, todayParts.day)) / 86400000;
  const status = remainingDays < 0
    ? 'expired'
    : remainingDays === 0
      ? 'expires-today'
      : remainingDays <= 7
        ? 'expiring'
        : 'valid';
  const labels = {
    en: {
      expired: 'Expired',
      'expires-today': 'Expires Today',
      expiring: 'Expiring Soon',
      valid: 'Not Expiring Soon'
    },
    kn: {
      expired: 'ಅವಧಿ ಮುಗಿದಿದೆ',
      'expires-today': 'ಇಂದು ಅವಧಿ ಮುಗಿಯುತ್ತದೆ',
      expiring: 'ಶೀಘ್ರದಲ್ಲೇ ಅವಧಿ ಮುಗಿಯುತ್ತದೆ',
      valid: 'ಶೀಘ್ರದಲ್ಲೇ ಅವಧಿ ಮುಗಿಯುವುದಿಲ್ಲ'
    }
  };
  const language = langToggle.value === 'kn' ? 'kn' : 'en';
  return { display, status, label: labels[language][status] };
}

function firstScanResult(data) {
  if (!Array.isArray(data) || !data.length) throw new Error('No medicine details were detected.');
  if (data[0].error && !data[0].medicine_name && !data[0].brand_name) throw new Error(data[0].error);
  return data[0];
}

function updateExpiryVerificationNotice() {
  if (!expiryVerificationNotice) return;
  expiryVerificationNotice.hidden = !pendingOcrExpiry;
  if (!pendingOcrExpiry) {
    expiryVerificationNotice.textContent = '';
    return;
  }
  const displayDate = formatExpiryDisplay(pendingOcrExpiry);
  expiryVerificationNotice.textContent = langToggle.value === 'kn'
    ? `OCR ಗುರುತಿಸಿದ ಮುಕ್ತಾಯ ದಿನಾಂಕ: ${displayDate}. ಉಳಿಸುವ ಮೊದಲು ಪ್ಯಾಕೇಜ್‌ನೊಂದಿಗೆ ಪರಿಶೀಲಿಸಿ.`
    : `OCR expiry detected: ${displayDate}. Verify this date against the package before saving.`;
}

async function scanStaffImage(file) {
  if (!file) throw new Error('Please upload a medicine image first.');
  const formData = new FormData();
  formData.append('images', file);
  formData.append('language', langToggle.value);
  const response = await fetch('/process', { method: 'POST', body: formData });
  const data = await response.json();
  if (!response.ok || data.error) throw new Error(data.error || 'Medicine scan failed.');
  return firstScanResult(data);
}

function fillStaffMedicineForm(result) {
  document.getElementById('medicineNameInput').value = result.medicine_name || result.generic_name || result.brand_name || '';
  document.getElementById('brandNameInput').value = result.brand_name || '';
  document.getElementById('genericNameInput').value = result.generic_name || '';
  document.getElementById('strengthInput').value = result.strength || '';
  document.getElementById('dosageFormInput').value = result.dosage_form || '';
  document.getElementById('expiryDateInput').value = formatExpiryForInput(result.expiry_date);
  pendingOcrExpiry = result.expiry_date &&
    !['NOT FOUND', 'Information not available'].includes(result.expiry_date)
    ? result.expiry_date
    : null;
  updateExpiryVerificationNotice();
}

function setStaffFieldsEditable(editable) {
  ['medicineNameInput', 'brandNameInput', 'genericNameInput', 'strengthInput', 'dosageFormInput', 'expiryDateInput']
    .forEach(id => { document.getElementById(id).readOnly = !editable; });
}

async function scanForStaffUpdate() {
  staffUpdateStatus.textContent = 'Scanning with YOLO, OCR and Gemini...';
  staffUpdateScanBtn.disabled = true;
  try {
    const result = await scanStaffImage(staffUpdateImageInput.files[0]);
    fillStaffMedicineForm(result);
    setStaffFieldsEditable(false);
    staffUpdateStatus.textContent = 'Details extracted. Enter quantity, row and column, then save.';
  } catch (error) {
    staffUpdateStatus.textContent = error.message;
  } finally {
    staffUpdateScanBtn.disabled = false;
  }
}

async function scanForLocation() {
  staffLocationStatus.textContent = 'Scanning medicine image...';
  staffLocationResult.hidden = true;
  staffLocationScanBtn.disabled = true;
  try {
    const result = await scanStaffImage(staffLocationImageInput.files[0]);
    const searchName = result.medicine_name || result.generic_name || result.brand_name;
    const response = await fetch(`/search-medicine?q=${encodeURIComponent(searchName)}`);
    const data = await response.json();
    if (!response.ok || !data.medicines || !data.medicines.length) throw new Error('Medicine was not found in inventory.');
    const medicine = data.medicines[0];
    staffLocationResult.innerHTML = `<strong>${escapeHtml(medicine.medicine_name)}</strong><span>LOCATION FOUND</span><span>Row: ${escapeHtml(medicine.row_number ?? 'Not stored')}</span><span>Column / Rack: ${escapeHtml(medicine.column_number ?? 'Not stored')}</span>`;
    staffLocationResult.hidden = false;
    staffLocationStatus.textContent = '';
  } catch (error) {
    staffLocationStatus.textContent = error.message;
  } finally {
    staffLocationScanBtn.disabled = false;
  }
}
function renderLocationResults(medicines) {
  staffLocationResult.innerHTML = medicines.map(medicine =>
    `<div class="staff-location-item"><strong>${escapeHtml(medicine.medicine_name)}</strong><span>LOCATION FOUND</span><span>Row: ${escapeHtml(medicine.row_number ?? 'Not stored')}</span><span>Column / Rack: ${escapeHtml(medicine.column_number ?? 'Not stored')}</span></div>`
  ).join('');
  staffLocationResult.hidden = false;
}

async function searchLocationByName() {
  const name = staffLocationSearchInput.value.trim();
  staffLocationResult.hidden = true;
  if (!name) { staffLocationStatus.textContent = 'Please enter a medicine name.'; return; }
  staffLocationStatus.textContent = 'Searching...';
  staffLocationSearchBtn.disabled = true;
  try {
    const response = await fetch(`/search-medicine?q=${encodeURIComponent(name)}`);
    const data = await response.json();
    if (!response.ok || !data.medicines || !data.medicines.length) throw new Error('Medicine was not found in inventory.');
    renderLocationResults(data.medicines);
    staffLocationStatus.textContent = '';
  } catch (error) {
    staffLocationStatus.textContent = error.message;
  } finally {
    staffLocationSearchBtn.disabled = false;
  }
}
async function saveStaffMedicine(event) {
  event.preventDefault();
  if (pendingOcrExpiry) {
    const expiryValue = formatExpiryDisplay(document.getElementById('expiryDateInput').value);
    const message = langToggle.value === 'kn'
      ? `OCR ಗುರುತಿಸಿದ ಮುಕ್ತಾಯ ದಿನಾಂಕ ${expiryValue}. ಉಳಿಸುವ ಮೊದಲು ಪ್ಯಾಕೇಜ್‌ನೊಂದಿಗೆ ಪರಿಶೀಲಿಸಿ. ಮುಂದುವರಿಸಬೇಕೆ?`
      : `OCR extracted expiry date ${expiryValue}. Verify it against the package before saving. Continue?`;
    if (!window.confirm(message)) return;
    pendingOcrExpiry = null;
    expiryVerificationNotice.hidden = true;
  }
  const formData = new FormData(addMedicineForm);
  const payload = Object.fromEntries(formData.entries());
  try {
    const response = await fetch('/add-medicine', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not save medicine.');
    staffUpdateStatus.textContent = 'Medicine saved to inventory.';
    addMedicineForm.reset();
    setStaffFieldsEditable(false);
    loadInventory();
    refreshExpiredMedicineStatus(false).catch(error => {
      console.error('Could not refresh expired medicine status:', error);
    });
  } catch (error) {
    staffUpdateStatus.textContent = error.message;
  }
}

function renderInventory(medicines) {
  inventoryTableBody.innerHTML = medicines.length ? medicines.map((medicine, index) => {
    const expiry = expiryPresentation(medicine.expiry_date);
    return `<tr><td>${index + 1}</td><td>${escapeHtml(medicine.medicine_name)}</td><td>${escapeHtml(medicine.strength || '')}</td><td><span>${escapeHtml(expiry.display)}</span>${expiry.status ? `<span class="expiry-status expiry-status-${expiry.status}">${escapeHtml(expiry.label)}</span>` : ''}</td><td>${escapeHtml(medicine.quantity ?? 0)}</td><td>${escapeHtml(medicine.row_number ?? '')}</td><td>${escapeHtml(medicine.column_number ?? '')}</td></tr>`;
  }).join('') : '<tr><td colspan="7" class="table-empty">No medicines in stock.</td></tr>';
}

async function loadInventory() {
  const response = await fetch('/medicines');
  const data = await response.json();
  renderInventory(data.medicines || []);
}

function renderAlertList(element, medicines, emptyText, withExpiryStatus = false, expiryNotifications = false) {
  element.innerHTML = medicines.length ? medicines.map(medicine => {
    const expiry = expiryPresentation(medicine.expiry_date);
    if (expiryNotifications) {
      const daysRemaining = medicine.days_remaining;
      const medicineName = escapeHtml(medicine.medicine_name);
      const days = Math.abs(daysRemaining);
      const dayLabel = `${days} ${days === 1 ? 'day' : 'days'}`;
      const warning = daysRemaining < 0
        ? `${medicineName} expired ${dayLabel} ago.`
        : daysRemaining === 0
          ? `${medicineName} expires today.`
          : daysRemaining === 1
            ? `${medicineName} expires tomorrow.`
            : `${medicineName} expires in ${dayLabel}.`;
      return `<div><strong>${warning}</strong><small>Expiry date: ${escapeHtml(expiry.display)}</small></div>`;
    }
    const status = withExpiryStatus && expiry.status
      ? `<span class="expiry-status expiry-status-${expiry.status}">${escapeHtml(expiry.label)}</span>`
      : '';
    return `<div>${escapeHtml(medicine.medicine_name)} ${status}<small>(${escapeHtml(expiry.display)} | Qty: ${escapeHtml(medicine.quantity)})</small></div>`;
  }).join('') : `<div class="empty-state">${emptyText}</div>`;
}

function renderExpiredMedicineList(element, medicines) {
  if (!element) return;
  element.textContent = '';
  if (!medicines.length) {
    const emptyState = document.createElement('div');
    emptyState.className = 'empty-state';
    emptyState.textContent = 'No expired medicines.';
    element.appendChild(emptyState);
    return;
  }

  medicines.forEach(medicine => {
    const item = document.createElement('div');
    item.className = 'expired-medicine-item';

    const medicineName = medicine.medicine_name || 'Unnamed medicine';
    const daysRemaining = Number(medicine.days_remaining);
    const expiredDays = Number.isFinite(daysRemaining) ? Math.abs(daysRemaining) : null;
    const title = document.createElement('strong');
    title.textContent = expiredDays === null
      ? `${medicineName} is expired.`
      : `${medicineName} expired ${expiredDays} ${expiredDays === 1 ? 'day' : 'days'} ago.`;
    item.appendChild(title);

    const details = [];
    if (medicine.brand_name) details.push(`Brand: ${medicine.brand_name}`);
    details.push(`Expiry date: ${formatExpiryDisplay(medicine.expiry_date) || 'Unavailable'}`);
    details.push(`Available stock: ${medicine.quantity ?? 'Not recorded'}`);

    const location = [];
    if (medicine.row_number !== null && medicine.row_number !== undefined && medicine.row_number !== '') {
      location.push(`Row ${medicine.row_number}`);
    }
    if (medicine.column_number !== null && medicine.column_number !== undefined && medicine.column_number !== '') {
      location.push(`Column ${medicine.column_number}`);
    }
    if (location.length) details.push(`Storage location: ${location.join(', ')}`);

    const detailText = document.createElement('p');
    detailText.textContent = details.join(' · ');
    item.appendChild(detailText);
    element.appendChild(item);
  });
}

async function refreshExpiredMedicineStatus(showPopup = false) {
  if (!expiredMedicineModal) return;

  const response = await fetch('/medicines/expired');
  if (!response.ok) {
    throw new Error(`Could not load expired medicines (HTTP ${response.status}).`);
  }
  const data = await response.json();
  if (!Array.isArray(data.medicines)) {
    throw new Error('Expired-medicine response did not contain a medicine list.');
  }

  const medicines = data.medicines;
  renderExpiredMedicineList(expiredList, medicines);
  renderExpiredMedicineList(expiredMedicineModalList, medicines);
  const expiredCount = document.getElementById('expiredCount');
  if (expiredCount) expiredCount.textContent = medicines.length;
  if (!medicines.length) {
    expiredMedicineWarning.textContent = '';
    return;
  }

  const count = medicines.length;
  expiredMedicineWarning.textContent =
    `WARNING! ${count} medicine${count === 1 ? '' : 's'} in your inventory ${count === 1 ? 'has' : 'have'} expired.`;
  if (showPopup && !expiredMedicinePopupShown) {
    expiredMedicinePopupShown = true;
    expiredMedicineModal.showModal();
  }
}

async function loadStaffAlerts() {
  const [expiring, expired, lowStock] = await Promise.all([
    fetch('/medicines/expiring').then(response => response.json()),
    fetch('/medicines/expired').then(response => response.json()),
    fetch('/medicines/low-stock').then(response => response.json())
  ]);
  renderAlertList(expiringList, expiring.medicines || [], 'No medicines nearing expiry.', false, true);
  renderExpiredMedicineList(expiredList, expired.medicines || []);
  renderAlertList(staffLowStockList, lowStock.medicines || [], 'No low-stock medicines.');
  document.getElementById('expiringCount').textContent = expiring.count ?? (expiring.medicines || []).length;
  document.getElementById('expiredCount').textContent = expired.count ?? (expired.medicines || []).length;
}

if (closeExpiredMedicineModal) {
  closeExpiredMedicineModal.addEventListener('click', () => expiredMedicineModal.close());
}
if (expiredMedicineModal) {
  refreshExpiredMedicineStatus(true).catch(error => {
    console.error('Could not load expired medicine dashboard alert:', error);
  });
}

if (staffUpdateScanBtn) staffUpdateScanBtn.addEventListener('click', scanForStaffUpdate);
if (langToggle) langToggle.addEventListener('change', updateExpiryVerificationNotice);
if (staffLocationScanBtn) staffLocationScanBtn.addEventListener('click', scanForLocation);
if (staffLocationSearchBtn) staffLocationSearchBtn.addEventListener('click', searchLocationByName);
if (staffLocationSearchInput) staffLocationSearchInput.addEventListener('keydown', e => { if (e.key === 'Enter') searchLocationByName(); });
if (addMedicineForm) addMedicineForm.addEventListener('submit', saveStaffMedicine);
if (editExtractedFieldsBtn) editExtractedFieldsBtn.addEventListener('click', () => {
  setStaffFieldsEditable(true);
  staffUpdateStatus.textContent = 'Edit the extracted details, then save the medicine.';
});
if (inventoryRefreshBtn) inventoryRefreshBtn.addEventListener('click', loadInventory);

// ==================== SELL MEDICINE & SALES HISTORY ====================
const sellMedicineForm = document.getElementById('sellMedicineForm');
const sellMedicineSelect = document.getElementById('sellMedicineSelect');
const sellQuantityInput = document.getElementById('sellQuantityInput');
const sellStockDetails = document.getElementById('sellStockDetails');
const sellStatus = document.getElementById('sellStatus');
const sellSubmitBtn = document.getElementById('sellSubmitBtn');
const salesHistoryTableBody = document.getElementById('salesHistoryTableBody');
const salesHistoryRefreshBtn = document.getElementById('salesHistoryRefreshBtn');
let sellMedicines = [];     // every batch (row) currently in inventory
let sellRequestId = null;   // one id per sale attempt; stops a double click selling twice
let sellInFlight = false;

function setSellStatus(message, kind = '') {
  sellStatus.textContent = message;
  sellStatus.classList.toggle('is-error', kind === 'error');
  sellStatus.classList.toggle('is-success', kind === 'success');
}

function isMedicineSellable(medicine) {
  return expiryPresentation(medicine.expiry_date).status !== 'expired' && Number(medicine.quantity) > 0;
}

function sellBatchLabel(medicine) {
  const expiry = expiryPresentation(medicine.expiry_date);
  const parts = [medicine.medicine_name];
  if (medicine.strength) parts.push(medicine.strength);
  parts.push(`Exp ${expiry.display}`, `Qty ${medicine.quantity ?? 0}`);
  let label = parts.join(' · ');
  if (expiry.status === 'expired') label += ' (EXPIRED - cannot sell)';
  else if (!(Number(medicine.quantity) > 0)) label += ' (out of stock)';
  return label;
}

function selectedSellMedicine() {
  const id = Number(sellMedicineSelect.value);
  return sellMedicines.find(medicine => medicine.id === id) || null;
}

function renderSellOptions(selectedId = '') {
  sellMedicineSelect.innerHTML = '';
  const placeholder = document.createElement('option');
  placeholder.value = '';
  placeholder.textContent = sellMedicines.length ? 'Select a medicine' : 'No medicines in stock';
  sellMedicineSelect.appendChild(placeholder);
  sellMedicines.forEach(medicine => {
    const option = document.createElement('option');
    option.value = String(medicine.id);
    option.textContent = sellBatchLabel(medicine);
    option.disabled = !isMedicineSellable(medicine);
    sellMedicineSelect.appendChild(option);
  });
  const stillThere = sellMedicines.some(medicine => String(medicine.id) === String(selectedId) && isMedicineSellable(medicine));
  sellMedicineSelect.value = stillThere ? String(selectedId) : '';
}

function showSellDetails() {
  const medicine = selectedSellMedicine();
  sellStockDetails.hidden = !medicine;
  if (!medicine) return;
  const expiry = expiryPresentation(medicine.expiry_date);
  document.getElementById('sellDetailName').textContent = medicine.medicine_name;
  document.getElementById('sellDetailStrength').textContent = medicine.strength || 'Not specified';
  document.getElementById('sellDetailExpiry').textContent = expiry.label ? `${expiry.display} (${expiry.label})` : expiry.display;
  document.getElementById('sellDetailQuantity').textContent = String(medicine.quantity ?? 0);
  sellQuantityInput.max = String(medicine.quantity ?? 0);
}

async function loadSellMedicines() {
  const response = await fetch('/medicines');
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Could not load medicines.');
  sellMedicines = data.medicines || [];
  renderSellOptions(sellMedicineSelect.value);
  showSellDetails();
}

function newSaleRequestId() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
  return `sale-${Date.now()}-${Math.random().toString(36).slice(2, 12)}`;
}

async function submitSale(event) {
  event.preventDefault();
  if (sellInFlight) return;

  const medicine = selectedSellMedicine();
  if (!medicine) return setSellStatus('Please select a medicine batch first.', 'error');
  if (expiryPresentation(medicine.expiry_date).status === 'expired') {
    return setSellStatus('This batch has expired and cannot be sold.', 'error');
  }

  const rawQuantity = sellQuantityInput.value.trim();
  if (!/^\d+$/.test(rawQuantity) || Number(rawQuantity) < 1) {
    return setSellStatus('Enter the quantity sold as a whole number of at least 1.', 'error');
  }
  const quantity = Number(rawQuantity);
  const available = Number(medicine.quantity) || 0;
  if (quantity > available) {
    return setSellStatus(`Insufficient stock. Available: ${available}, requested: ${quantity}.`, 'error');
  }

  sellInFlight = true;
  sellSubmitBtn.disabled = true;
  setSellStatus('Completing sale...');
  if (!sellRequestId) sellRequestId = newSaleRequestId();
  let serverResponded = false;
  try {
    const response = await fetch('/sales', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ medicine_id: medicine.id, quantity, request_id: sellRequestId })
    });
    serverResponded = true;
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'The sale could not be completed.');

    sellRequestId = null;
    // Show the new quantity straight away, then confirm it from the database.
    medicine.quantity = data.remaining_stock;
    renderSellOptions(String(medicine.id));
    showSellDetails();
    sellQuantityInput.value = '';
    setSellStatus(data.message, 'success');
    loadSellMedicines().catch(error => console.error('Could not refresh stock:', error));
    loadInventory().catch(error => console.error('Could not refresh inventory:', error));
    loadSalesHistory().catch(error => console.error('Could not refresh sales history:', error));
  } catch (error) {
    if (serverResponded) sellRequestId = null; // the server refused it, so a retry is a new sale
    setSellStatus(error instanceof TypeError ? 'Could not reach the server. Check your connection and try again.' : error.message, 'error');
    if (serverResponded) loadSellMedicines().catch(() => {});
  } finally {
    sellInFlight = false;
    sellSubmitBtn.disabled = false;
  }
}

function formatSaleDateTime(soldAt) {
  const [datePart = '', timePart = ''] = String(soldAt || '').split(' ');
  const [year, month, day] = datePart.split('-');
  const [hours, minutes] = timePart.split(':').map(Number);
  if (!year || !month || !day || Number.isNaN(hours)) return { date: String(soldAt || ''), time: '' };
  const suffix = hours >= 12 ? 'PM' : 'AM';
  const hour12 = hours % 12 || 12;
  return {
    date: `${day}/${month}/${year}`,
    time: `${String(hour12).padStart(2, '0')}:${String(minutes).padStart(2, '0')} ${suffix}`
  };
}

function renderSalesHistory(sales) {
  salesHistoryTableBody.innerHTML = sales.length ? sales.map(sale => {
    const when = formatSaleDateTime(sale.sold_at);
    const strength = sale.strength ? `<small>${escapeHtml(sale.strength)}</small>` : '';
    return `<tr><td>${escapeHtml(sale.medicine_name)}${strength}</td><td>${escapeHtml(sale.quantity_sold)}</td><td>${escapeHtml(when.date)}</td><td>${escapeHtml(when.time)}</td></tr>`;
  }).join('') : '<tr><td colspan="4" class="table-empty">No sales recorded yet.</td></tr>';
}

async function loadSalesHistory() {
  const response = await fetch('/sales');
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Could not load sales history.');
  renderSalesHistory(data.sales || []);
}

if (sellMedicineForm) sellMedicineForm.addEventListener('submit', submitSale);
if (sellMedicineSelect) sellMedicineSelect.addEventListener('change', () => {
  sellRequestId = null;
  setSellStatus('');
  showSellDetails();
});
if (sellQuantityInput) sellQuantityInput.addEventListener('input', () => {
  sellRequestId = null;
  if (sellStatus.classList.contains('is-error')) setSellStatus('');
});
if (salesHistoryRefreshBtn) salesHistoryRefreshBtn.addEventListener('click', () => {
  loadSalesHistory().catch(error => console.error('Could not load sales history:', error));
});
