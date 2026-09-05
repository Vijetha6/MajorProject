const imageInput = document.getElementById('imageInput');
const preview = document.getElementById('preview');
const submitBtn = document.getElementById('submitBtn');
const output = document.getElementById('output');
const langToggle = document.getElementById('langToggle');
const loading = document.getElementById('loading');
const tabAnalyzer = document.getElementById('tabAnalyzer');
const tabGenerator = document.getElementById('tabGenerator');
const analyzerTab = document.getElementById('analyzerTab');
const generatorTab = document.getElementById('generatorTab');
const generateBtn = document.getElementById('generateBtn');
const prescriptionText = document.getElementById('prescriptionText');
const generatorOutput = document.getElementById('generatorOutput');
const recordSpeechBtn = document.getElementById('recordSpeechBtn');
const speechStatus = document.getElementById('speechStatus');
let recognition = null;
let recognizing = false;


document.querySelector('.upload-btn').addEventListener('click', (e) => {
  e.preventDefault();
  imageInput.click();
});


imageInput.addEventListener('change', () => {
  const file = imageInput.files[0];
  if (!file) return;
  
  const reader = new FileReader();
  reader.onload = (e) => {
    preview.src = e.target.result;
    preview.style.display = 'block';
  };
  reader.readAsDataURL(file);
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

async function generatePrescription() {

    const patientName = document.getElementById("patientName").value.trim();
    const patientAge = document.getElementById("patientAge").value.trim();
    const patientGender = document.getElementById("patientGender").value.trim();
    const patientPhone = document.getElementById("patientPhone").value.trim();
    const text = prescriptionText.value.trim();

    if (!patientName) {
        showGeneratorError("Please enter patient name.");
        return;
    }

    if (!patientAge) {
        showGeneratorError("Please enter patient age.");
        return;
    }

    if (isNaN(patientAge) || patientAge < 1 || patientAge > 150) {
        showGeneratorError("Please enter a valid age (1-150).");
        return;
    }

    if (!patientGender) {
        showGeneratorError("Please select patient gender.");
        return;
    }

    if (!/^[6-9]\d{9}$/.test(patientPhone)) {
        showGeneratorError("Please enter a valid 10-digit mobile number.");
        return;
    }

    if (!text) {
        showGeneratorError("Please enter prescription text.");
        return;
    }

    generateBtn.disabled = true;
    generateBtn.textContent = "Generating...";
    generatorOutput.innerHTML = "";

    try {

        const res = await fetch("/generate-prescription", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                patient_name: patientName,
                age: patientAge,
                gender: patientGender,
                phone_number: patientPhone,
                text: text
            })
        });

        const raw = await res.text();
        let data;

        try {
            data = JSON.parse(raw);
        } catch (parseErr) {
            showGeneratorError(`Server returned invalid JSON:\n${raw}`);
            console.error('Invalid JSON response from /generate-prescription:', raw);
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

        generatorOutput.innerHTML = `
            <div class="medicine-card">
                <h3>✅ Prescription Generated</h3>

                <p><b>Patient:</b> ${escapeHtml(data.patient)}</p>
                <p><b>Mobile:</b> ${escapeHtml(data.phone_number)}</p>
                <p><b>Age:</b> ${escapeHtml(data.age)}</p>
                <p><b>Gender:</b> ${escapeHtml(data.gender)}</p>

                <br>

                <a href="${escapeHtml(data.download_url)}" target="_blank">
                    Download Prescription PDF
                </a>
            </div>
        `;

    } catch (err) {

        showGeneratorError(err.message);

    } finally {

        generateBtn.disabled = false;
        generateBtn.textContent = "Generate Prescription PDF";

    }
}

function switchTab(tab) {
  if (tab === 'analyzer') {
    tabAnalyzer.classList.add('active');
    tabGenerator.classList.remove('active');
    analyzerTab.classList.add('active');
    generatorTab.classList.remove('active');
  } else {
    tabAnalyzer.classList.remove('active');
    tabGenerator.classList.add('active');
    analyzerTab.classList.remove('active');
    generatorTab.classList.add('active');
  }
}

tabAnalyzer.addEventListener('click', () => switchTab('analyzer'));
tabGenerator.addEventListener('click', () => switchTab('generator'));
generateBtn.addEventListener('click', generatePrescription);
recordSpeechBtn.addEventListener('click', toggleSpeechRecognition);

switchTab('analyzer');

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
      prescriptionText.value += (prescriptionText.value ? '\n' : '') + transcript.trim();
      speechStatus.textContent = '✅ Speech captured. Continue speaking or click Stop to finish.';
    }
  };

  recognition.onerror = (event) => {
    speechStatus.textContent = `❌ Speech recognition error: ${event.error}`;
  };

  recognition.onend = () => {
    recognizing = false;
    recordSpeechBtn.textContent = '🎙️ Record Prescription';
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