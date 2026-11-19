const isBrowser = typeof window !== 'undefined' && typeof document !== 'undefined';
const imageInput = isBrowser ? document.getElementById('imageInput') : null;
const preview = isBrowser ? document.getElementById('preview') : null;
const previewContainer = isBrowser ? document.getElementById('previewContainer') : null;
const submitBtn = isBrowser ? document.getElementById('submitBtn') : null;
const output = isBrowser ? document.getElementById('output') : null;
const fileSummary = isBrowser ? document.getElementById('fileSummary') : null;
const langToggle = isBrowser ? document.getElementById('langToggle') : null;
const loading = isBrowser ? document.getElementById('loading') : null;
const generateBtn = isBrowser ? document.getElementById('generateBtn') : null;
const generatorOutput = isBrowser ? document.getElementById('generatorOutput') : null;
const recordSpeechBtn = isBrowser ? document.getElementById('recordSpeechBtn') : null;
const speechStatus = isBrowser ? document.getElementById('speechStatus') : null;
let selectedPatient = null;
let selectedPatientVisits = [];

let recognition = null;
let recognizing = false;
let recordingActive = false; // NEW: Track if doctor wants to continue recording
let finalTranscript = '';
let interimTranscript = '';
let recognitionResultKeys = new Set();
let recognitionSessionToken = 0;
let micStream = null;
let audioContext = null;
let analyserNode = null;
let vadAnimationFrame = null;
let silenceTimer = null;
let silenceStartedAt = null;
let lastAudioLevel = 0;
let lastSpeechDetectedAt = null; // NEW: Track when we last detected speech
let hasDetectedSpeech = false; // NEW: Track if ANY speech has been detected
let speechActivityDetected = false; // NEW: Track speech activity from recognition events

const speechConfig = {
  silenceDurationMs: 3000, // 3 seconds of silence
  voiceThreshold: 0.08,
  noiseFloor: 0.02,
  smoothingTimeConstant: 0.18,
  autoRestartDelay: 100 // Delay before auto-restart on recognition.onend
};

function normalizeTranscriptText(text) {
  if (!text) return '';
  return String(text)
    .replace(/\s+/g, ' ')
    .replace(/\s+(?=[.,;:!?])/g, '')
    .trim();
}

function appendTranscriptSegment(existingText, nextText) {
  const current = normalizeTranscriptText(existingText || '');
  const next = normalizeTranscriptText(nextText || '');
  if (!current && !next) return '';
  if (!current) return next;
  if (!next) return current;
  return `${current} ${next}`.replace(/\s+/g, ' ').trim();
}

function buildLiveTranscript(finalText, interimText) {
  const combined = [normalizeTranscriptText(finalText), normalizeTranscriptText(interimText)]
    .filter(Boolean)
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim();
  return combined;
}

function deduplicateTranscript(rawTranscript) {
  const rawItems = rawTranscript
    .split(/(?<=[.!?])\s+|\n+/)
    .map(item => normalizeTranscriptText(item))
    .filter(Boolean);

  const seen = new Set();
  const deduped = [];

  rawItems.forEach((item) => {
    const key = item.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      deduped.push(item);
    }
  });

  return deduped.join(' ');
}

function getAudioLevel(analyser) {
  if (!analyser) return 0;
  const buffer = new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(buffer);
  let sum = 0;
  for (let i = 0; i < buffer.length; i += 1) {
    const sample = (buffer[i] - 128) / 128;
    sum += sample * sample;
  }
  return Math.sqrt(sum / buffer.length);
}

function evaluateSilenceState(audioLevel, currentState) {
  if (audioLevel >= speechConfig.voiceThreshold + speechConfig.noiseFloor) {
    return {
      ...currentState,
      speechDetected: true,
      silenceStartedAt: null,
      lastAudioLevel: audioLevel,
      status: 'Voice detected.'
    };
  }

  if (currentState.speechDetected) {
    const silenceStart = currentState.silenceStartedAt || Date.now();
    const elapsed = Date.now() - silenceStart;
    if (elapsed >= speechConfig.silenceDurationMs) {
      return {
        ...currentState,
        speechDetected: false,
        silenceStartedAt: silenceStart,
        lastAudioLevel: audioLevel,
        status: 'Silence detected – stopping in 3 seconds.'
      };
    }
    return {
      ...currentState,
      speechDetected: false,
      silenceStartedAt: silenceStart,
      lastAudioLevel: audioLevel,
      status: 'Silence detected – stopping in 3 seconds.'
    };
  }

  return {
    ...currentState,
    speechDetected: false,
    silenceStartedAt: currentState.silenceStartedAt || Date.now(),
    lastAudioLevel: audioLevel,
    status: 'Ready to record.'
  };
}

function isLikelyMedicineName(text) {
  if (!text || text.length < 2) return false;
  
  const textLower = text.toLowerCase().trim();
  
  // Only exclude very obvious non-medicine phrases
  const excludePhrases = [
    'hello doctor speaking i am',
    'recording completed',
    'take adequate rest',
    'drink plenty of water',
    'patient should',
    'good morning good afternoon'
  ];
  
  for (const phrase of excludePhrases) {
    if (textLower.includes(phrase)) return false;
  }
  
  // Accept if it has ANY medicine indicators
  const hasDosage = /\d+\s*(?:mg|ml|mcg|g|milligram|mill)\b/i.test(text);
  const hasFrequency = /\b(once|twice|thrice|daily|weekly|per day|a day)\b/i.test(text);
  const hasDuration = /\bfor\s+\d+\s*(day|days|week|weeks)\b/i.test(text);
  const hasMedicineForm = /\b(tablet|capsule|syrup|injection)\b/i.test(text);
  
  // Common medicine name patterns
  const knownMedicines = [
    'paracetamol', 'amoxicillin', 'crocin', 'dolo', 'cetirizine',
    'amlodipine', 'metformin', 'aspirin', 'ibuprofen', 'omeprazole',
    'azithromycin', 'ciprofloxacin', 'amoxycillin', 'belov', 'belov'
  ];
  
  const hasKnownMedicine = knownMedicines.some(med => textLower.includes(med));
  
  // Accept if it has dosage OR known medicine OR frequency+duration
  return hasKnownMedicine || hasDosage || (hasFrequency && hasDuration) || (hasDosage && hasFrequency);
}

function parseMedicineLine(line) {
  const text = normalizeTranscriptText(line);
  if (!text || text.length < 3) return null;
  
  // First check if it even looks like medicine
  if (!isLikelyMedicineName(text)) return null;

  // Extract medicine name - look for word before dosage or frequency
  let nameMatch = text.match(/^(?:prescribe|prescribed)?\s*([A-Za-z][A-Za-z0-9 .()-]{1,}?)(?=\s+(?:\d+(?:\/\d+)?\s*(?:mg|ml|mcg|g|milligram|mill)|once|twice|thrice|daily|weekly))/i);
  
  if (!nameMatch) {
    // Try to match known medicine names explicitly
    const knownMedicines = ['paracetamol', 'amoxicillin', 'crocin', 'dolo', 'cetirizine', 'amlodipine', 'metformin', 'aspirin', 'ibuprofen', 'omeprazole', 'azithromycin', 'ciprofloxacin', 'amoxycillin', 'belov', 'belov', 'belov'];
    for (const med of knownMedicines) {
      const medRegex = new RegExp(`\\b(${med})\\b`, 'i');
      const match = text.match(medRegex);
      if (match) {
        nameMatch = {1: match[1]};
        break;
      }
    }
  }
  
  if (!nameMatch) {
    // Last resort: take first 1-3 words that look like a medicine name
    const words = text.split(/\s+/);
    let candidateName = '';
    for (let i = 0; i < Math.min(3, words.length); i++) {
      const word = words[i];
      // Skip filler words
      if (/^(the|for|in|on|at|to|a|an|prescribe|prescribed|patient|should|take|tablet|capsule)$/i.test(word)) {
        continue;
      }
      // Accept words that look like medicine names
      if (/^[A-Za-z]{3,}/.test(word)) {
        candidateName = word;
        break;
      }
    }
    if (candidateName && candidateName.length >= 3) {
      nameMatch = {1: candidateName};
    } else {
      return null;
    }
  }

  let name = nameMatch[1].trim();
  
  // Clean up medicine name
  name = name.replace(/\b(prescribe|prescribed|tablet|capsule|syrup|doctor|speaking|uh|um|the|mg|ml)\b/ig, '').trim();
  if (!name || name.length < 2) return null;

  const dosageMatch = text.match(/(\d+(?:\/\d+)?\s*(?:mg|ml|mcg|g|milligram|milligrams|mill))/i);
  let dosage = dosageMatch ? dosageMatch[1].trim() : 'Dose not specified';
  
  // Normalize dosage
  dosage = dosage.replace(/\bmilligram(?:s)?\b/ig, 'mg').replace(/\bmill\b/ig, 'mg');

  // Extract frequency
  let frequency = 'As directed';
  if (/\b(?:once|one time|1)\s+(?:daily|a day|per day|in a day|in the morning)\b/i.test(text)) {
    frequency = 'Once daily';
  } else if (/\b(?:twice|two times|2)\s+(?:daily|a day|per day|in a day)\b/i.test(text)) {
    frequency = 'Twice daily';
  } else if (/\b(?:thrice|three times|3)\s+(?:daily|a day|per day|in a day)\b/i.test(text)) {
    frequency = 'Thrice daily';
  } else if (/\b(?:four times|4 times)\s+(?:daily|a day|per day)\b/i.test(text)) {
    frequency = 'Four times daily';
  }

  // Extract duration
  let duration = 'As directed';
  const durationMatch = text.match(/for\s+(\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:day|days|week|weeks|month|months)/i);
  if (durationMatch) {
    duration = normalizeTranscriptText(durationMatch[0].replace(/^for\s+/i, ''));
    duration = duration.charAt(0).toUpperCase() + duration.slice(1);
  }

  // Extract timing (Morning, Afternoon, Evening, Bedtime)
  const timing = [];
  if (/\b(morning|in the morning)\b/i.test(text)) timing.push('Morning');
  if (/\b(afternoon|in the afternoon)\b/i.test(text)) timing.push('Afternoon');
  if (/\b(evening|in the evening)\b/i.test(text)) timing.push('Evening');
  if (/\b(bedtime|night|before bed|before sleep)\b/i.test(text)) timing.push('Bedtime');
  
  // Extract food instruction
  const foodMatch = text.match(/(after food|before food|with food|empty stomach|after meal|before meal|after the food)/i);
  const food_instruction = foodMatch ? foodMatch[1].trim() : '';

  // Extract special instructions (excluding parsed elements)
  let instructions = text;
  instructions = instructions.replace(new RegExp(name, 'ig'), '');
  if (dosage !== 'Dose not specified') {
    instructions = instructions.replace(new RegExp(dosage.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'ig'), '');
  }
  instructions = instructions.replace(/\b(prescribe|prescribed|morning|afternoon|evening|bedtime|after food|before food|with food|take|tablet|capsule|daily|weekly|uh|um|once|twice|thrice|for|day|days|week|weeks|the|patient|should)\b/ig, ' ');
  instructions = instructions.replace(/[.,;]+/g, ' ');
  instructions = normalizeTranscriptText(instructions);
  if (!instructions || instructions.length < 3) instructions = '';

  return {
    name: name.charAt(0).toUpperCase() + name.slice(1),
    dosage,
    frequency: frequency,
    duration: duration,
    timing,
    food_instruction,
    special_instructions: instructions,
    instructions
  };
}

function getStructuredMedicinesFromText(rawText) {
  const text = normalizeTranscriptText(rawText || '');
  if (!text) return [];

  // Split by medicine separators - be more generous
  const segments = text
    .split(/(?:\.{1,}|\balso prescribe\b|\band prescribe\b|\bprescribed?\b|\bfor the second medicine\b|\bsecond medicine\b|\bfirst medicine\b)\s+/i)
    .map(item => normalizeTranscriptText(item))
    .filter(Boolean);

  const medicines = [];
  const seenNames = new Set(); // Prevent duplicates
  
  for (const segment of segments) {
    const parsed = parseMedicineLine(segment);
    if (parsed && parsed.name && parsed.name.length > 2) {
      const nameKey = parsed.name.toLowerCase();
      // Only add if not already added
      if (!seenNames.has(nameKey)) {
        medicines.push(parsed);
        seenNames.add(nameKey);
      }
    }
  }

  return medicines;
}

let cachedMedicines = [];
let cachedGeneralAdvice = [];
let extractionSource = 'client';
let isExtracting = false;

async function extractPrescriptionIntelligently(text) {
  if (!text || !text.trim()) {
    return { medicines: [], general_advice: [], extraction_source: 'client' };
  }

  try {
    const response = await fetch('/extract-prescription', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text.trim() })
    });

    if (!response.ok) {
      console.warn('Server extraction failed, using client-side fallback');
      return { 
        medicines: getStructuredMedicinesFromText(text), 
        general_advice: [],
        extraction_source: 'client'
      };
    }

    const data = await response.json();
    return {
      medicines: data.medicines || [],
      general_advice: data.general_advice || [],
      extraction_source: data.extraction_source || 'unknown',
      note: data.note || ''
    };
  } catch (error) {
    console.error('Extraction error:', error);
    return { 
      medicines: getStructuredMedicinesFromText(text), 
      general_advice: [],
      extraction_source: 'client'
    };
  }
}

async function renderStructuredPrescriptionPreview() {
  const field = document.getElementById('prescriptionText');
  const preview = document.getElementById('structuredPrescriptionPreview');
  if (!field || !preview) return;

  const text = field.value.trim();

  if (!text) {
    preview.innerHTML = '<p class="preview-title">Structured medicine preview</p><div class="preview-empty">No medicine details detected yet. Speak or type a prescription to preview it here.</div>';
    cachedMedicines = [];
    cachedGeneralAdvice = [];
    return;
  }

  // Show loading state
  if (isExtracting) return;
  isExtracting = true;
  
  const loadingHtml = '<p class="preview-title">Structured medicine preview</p><div class="preview-empty">🔄 Analyzing prescription with AI...</div>';
  preview.innerHTML = loadingHtml;

  // Use intelligent extraction
  const result = await extractPrescriptionIntelligently(text);
  const medicines = result.medicines || [];
  const generalAdvice = result.general_advice || [];
  extractionSource = result.extraction_source || 'client';
  
  cachedMedicines = medicines;
  cachedGeneralAdvice = generalAdvice;
  
  isExtracting = false;

  if (!medicines.length && !generalAdvice.length) {
    let emptyMessage = 'No medicine details detected yet. Speak or type a prescription to preview it here.';
    if (result.note) {
      emptyMessage = `${result.note}<br><br>No medicines detected.`;
    }
    preview.innerHTML = `<p class="preview-title">Structured medicine preview</p><div class="preview-empty">${emptyMessage}</div>`;
    return;
  }

  const timingSlots = ['Morning', 'Afternoon', 'Evening', 'Bedtime'];
  
  let sourceIndicator = '';
  if (extractionSource === 'gemini') {
    sourceIndicator = '<span class="extraction-indicator extraction-ai">✓ AI-powered extraction</span>';
  } else if (extractionSource === 'fallback') {
    sourceIndicator = '<span class="extraction-indicator extraction-fallback">⚠ Pattern-based fallback</span>';
  } else {
    sourceIndicator = '<span class="extraction-indicator extraction-client">Client-side parsing</span>';
  }
  
  let html = `<p class="preview-title">Structured medicine preview ${sourceIndicator}</p>`;
  
  if (result.note) {
    html += `<div class="preview-note">${escapeHtml(result.note)}</div>`;
  }
  
  if (medicines.length > 0) {
    html += medicines.map((medicine, idx) => {
      // Highlight missing or uncertain information
      const nameClass = medicine.name && medicine.name.length > 2 ? '' : 'field-warning';
      const dosageClass = medicine.dosage && medicine.dosage !== 'Dose not specified' ? '' : 'field-warning';
      
      return `
        <div class="preview-medicine">
          <div class="preview-medicine-header">
            <h4>Medicine ${idx + 1}</h4>
            <button type="button" class="remove-medicine-btn" data-index="${idx}" title="Remove this medicine">×</button>
          </div>
          <div class="preview-grid">
            <label class="${nameClass}">Medicine name<input data-field="name" data-index="${idx}" value="${escapeHtml(medicine.name)}" placeholder="Required" /></label>
            <label class="${dosageClass}">Dosage<input data-field="dosage" data-index="${idx}" value="${escapeHtml(medicine.dosage)}" placeholder="e.g., 500 mg" /></label>
            <label>Frequency<select data-field="frequency" data-index="${idx}">
              <option value="As directed" ${medicine.frequency === 'As directed' ? 'selected' : ''}>As directed</option>
              <option value="Once daily" ${medicine.frequency === 'Once daily' ? 'selected' : ''}>Once daily</option>
              <option value="Twice daily" ${medicine.frequency === 'Twice daily' ? 'selected' : ''}>Twice daily</option>
              <option value="Thrice daily" ${medicine.frequency === 'Thrice daily' ? 'selected' : ''}>Thrice daily</option>
              <option value="Four times daily" ${medicine.frequency === 'Four times daily' ? 'selected' : ''}>Four times daily</option>
              <option value="Once weekly" ${medicine.frequency === 'Once weekly' ? 'selected' : ''}>Once weekly</option>
              <option value="Twice weekly" ${medicine.frequency === 'Twice weekly' ? 'selected' : ''}>Twice weekly</option>
            </select></label>
            <label>Duration<input data-field="duration" data-index="${idx}" value="${escapeHtml(medicine.duration)}" placeholder="e.g., 5 days" /></label>
          </div>
          <div class="preview-timing">
            <span class="timing-label">Timing:</span>
            ${timingSlots.map(slot => `<label><input type="checkbox" data-field="timing" data-index="${idx}" data-slot="${slot}" ${(medicine.timing || []).includes(slot) ? 'checked' : ''} /> ${slot}</label>`).join('')}
          </div>
          <div class="preview-grid">
            <label>Food instruction<input data-field="food_instruction" data-index="${idx}" value="${escapeHtml(medicine.food_instruction || '')}" placeholder="e.g., After food" /></label>
            <label>Additional instructions<input data-field="special_instructions" data-index="${idx}" value="${escapeHtml(medicine.special_instructions || '')}" placeholder="Optional notes" /></label>
          </div>
        </div>
      `;
    }).join('');
  }
  
  if (generalAdvice.length > 0) {
    html += `
      <div class="preview-general-advice">
        <h4>General patient advice</h4>
        <ul>${generalAdvice.map(advice => `<li>${escapeHtml(advice)}</li>`).join('')}</ul>
        <p class="advice-note">This advice will not be included in the prescription medicines list.</p>
      </div>
    `;
  }
  
  preview.innerHTML = html;
  
  // Add event listeners for remove buttons
  preview.querySelectorAll('.remove-medicine-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const index = parseInt(e.target.dataset.index);
      cachedMedicines.splice(index, 1);
      renderStructuredPrescriptionPreview();
    });
  });
}

function collectStructuredMedicines() {
  const preview = document.getElementById('structuredPrescriptionPreview');
  if (!preview) {
    // Fallback: use client-side extraction if preview doesn't exist
    return getStructuredMedicinesFromText(document.getElementById('prescriptionText')?.value || '');
  }

  const medicineCards = preview.querySelectorAll('.preview-medicine');
  if (!medicineCards.length) {
    // No cards rendered, return cached or client-side extracted
    if (cachedMedicines.length > 0) {
      return cachedMedicines;
    }
    return getStructuredMedicinesFromText(document.getElementById('prescriptionText')?.value || '');
  }

  // Collect from rendered preview cards (user may have edited)
  return Array.from(medicineCards).map((card, index) => {
    const getValue = (field) => {
      const elem = card.querySelector(`[data-field="${field}"][data-index="${index}"]`);
      return elem?.value || '';
    };
    const selectedTiming = Array.from(card.querySelectorAll(`[data-field="timing"][data-index="${index}"]:checked`)).map(item => item.dataset.slot);
    return {
      name: getValue('name').trim(),
      dosage: getValue('dosage').trim(),
      frequency: getValue('frequency').trim() || 'As directed',
      duration: getValue('duration').trim() || 'As directed',
      timing: selectedTiming,
      food_instruction: getValue('food_instruction').trim(),
      special_instructions: getValue('special_instructions').trim(),
      instructions: getValue('special_instructions').trim(),
    };
  }).filter(item => item.name && item.name.length > 1); // Only include medicines with valid names
}

const addMedicineBtn = isBrowser ? document.getElementById('addMedicineBtn') : null;
if (addMedicineBtn) {
  addMedicineBtn.addEventListener('click', async () => {
    // Add a blank medicine to the cached list and re-render
    const newMedicine = {
      name: '',
      dosage: 'Dose not specified',
      frequency: 'As directed',
      duration: 'As directed',
      timing: [],
      food_instruction: '',
      special_instructions: ''
    };
    cachedMedicines.push(newMedicine);
    
    // Re-render immediately without extraction
    const preview = document.getElementById('structuredPrescriptionPreview');
    if (preview) {
      const timingSlots = ['Morning', 'Afternoon', 'Evening', 'Bedtime'];
      const medicines = cachedMedicines;
      
      let sourceIndicator = '';
      if (extractionSource === 'gemini') {
        sourceIndicator = '<span class="extraction-indicator extraction-ai">✓ AI-powered extraction</span>';
      } else if (extractionSource === 'fallback') {
        sourceIndicator = '<span class="extraction-indicator extraction-fallback">⚠ Pattern-based fallback</span>';
      } else {
        sourceIndicator = '<span class="extraction-indicator extraction-client">Client-side parsing</span>';
      }
      
      let html = `<p class="preview-title">Structured medicine preview ${sourceIndicator}</p>`;
      
      html += medicines.map((medicine, idx) => {
        const nameClass = medicine.name && medicine.name.length > 2 ? '' : 'field-warning';
        const dosageClass = medicine.dosage && medicine.dosage !== 'Dose not specified' ? '' : 'field-warning';
        
        return `
          <div class="preview-medicine">
            <div class="preview-medicine-header">
              <h4>Medicine ${idx + 1}</h4>
              <button type="button" class="remove-medicine-btn" data-index="${idx}" title="Remove this medicine">×</button>
            </div>
            <div class="preview-grid">
              <label class="${nameClass}">Medicine name<input data-field="name" data-index="${idx}" value="${escapeHtml(medicine.name)}" placeholder="Required" /></label>
              <label class="${dosageClass}">Dosage<input data-field="dosage" data-index="${idx}" value="${escapeHtml(medicine.dosage)}" placeholder="e.g., 500 mg" /></label>
              <label>Frequency<select data-field="frequency" data-index="${idx}">
                <option value="As directed" ${medicine.frequency === 'As directed' ? 'selected' : ''}>As directed</option>
                <option value="Once daily" ${medicine.frequency === 'Once daily' ? 'selected' : ''}>Once daily</option>
                <option value="Twice daily" ${medicine.frequency === 'Twice daily' ? 'selected' : ''}>Twice daily</option>
                <option value="Thrice daily" ${medicine.frequency === 'Thrice daily' ? 'selected' : ''}>Thrice daily</option>
                <option value="Four times daily" ${medicine.frequency === 'Four times daily' ? 'selected' : ''}>Four times daily</option>
                <option value="Once weekly" ${medicine.frequency === 'Once weekly' ? 'selected' : ''}>Once weekly</option>
                <option value="Twice weekly" ${medicine.frequency === 'Twice weekly' ? 'selected' : ''}>Twice weekly</option>
              </select></label>
              <label>Duration<input data-field="duration" data-index="${idx}" value="${escapeHtml(medicine.duration)}" placeholder="e.g., 5 days" /></label>
            </div>
            <div class="preview-timing">
              <span class="timing-label">Timing:</span>
              ${timingSlots.map(slot => `<label><input type="checkbox" data-field="timing" data-index="${idx}" data-slot="${slot}" ${(medicine.timing || []).includes(slot) ? 'checked' : ''} /> ${slot}</label>`).join('')}
            </div>
            <div class="preview-grid">
              <label>Food instruction<input data-field="food_instruction" data-index="${idx}" value="${escapeHtml(medicine.food_instruction || '')}" placeholder="e.g., After food" /></label>
              <label>Additional instructions<input data-field="special_instructions" data-index="${idx}" value="${escapeHtml(medicine.special_instructions || '')}" placeholder="Optional notes" /></label>
            </div>
          </div>
        `;
      }).join('');
      
      if (cachedGeneralAdvice.length > 0) {
        html += `
          <div class="preview-general-advice">
            <h4>General patient advice</h4>
            <ul>${cachedGeneralAdvice.map(advice => `<li>${escapeHtml(advice)}</li>`).join('')}</ul>
            <p class="advice-note">This advice will not be included in the prescription medicines list.</p>
          </div>
        `;
      }
      
      preview.innerHTML = html;
      
      // Add event listeners for remove buttons
      preview.querySelectorAll('.remove-medicine-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
          const index = parseInt(e.target.dataset.index);
          cachedMedicines.splice(index, 1);
          renderStructuredPrescriptionPreview();
        });
      });
      
      // Focus on the new medicine name field
      const newMedicineIndex = medicines.length - 1;
      const nameInput = preview.querySelector(`[data-field="name"][data-index="${newMedicineIndex}"]`);
      if (nameInput) {
        nameInput.focus();
      }
    }
  });
}

const removeMedicineBtn = isBrowser ? document.getElementById('removeMedicineBtn') : null;
if (removeMedicineBtn) {
  removeMedicineBtn.addEventListener('click', () => {
    if (cachedMedicines.length > 0) {
      cachedMedicines.pop();
      renderStructuredPrescriptionPreview();
    }
  });
}

if (isBrowser) {
  const uploadButton = document.querySelector('.upload-btn');
  if (uploadButton && imageInput) {
    uploadButton.addEventListener('click', (e) => {
      e.preventDefault();
      imageInput.click();
    });
  }

  if (imageInput && previewContainer) {
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
  }

  const uploadZone = document.querySelector('.upload-btn');
  if (uploadZone) {
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
  }
}

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
  const medicines = collectStructuredMedicines();
  if (!medicines.length) throw new Error('Enter at least one valid medicine before saving.');
  return { text: prescriptionText, medicines };
}

const prescriptionTextField = document.getElementById('prescriptionText');
if (prescriptionTextField) {
  let extractionTimeout;
  prescriptionTextField.addEventListener('input', () => {
    generateBtn.disabled = !prescriptionTextField.value.trim();
    
    // Debounce intelligent extraction (wait 1.5 seconds after user stops typing)
    clearTimeout(extractionTimeout);
    extractionTimeout = setTimeout(() => {
      renderStructuredPrescriptionPreview();
    }, 1500);
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
      ...prescription,
      medicines: prescription.medicines || []
    };
    const response = await fetch('/generate-prescription', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Failed to save prescription (HTTP ${response.status}).`);

    // DEBUG: Log the response data
    console.log('[WhatsApp Debug] Backend response:', data);
    console.log('[WhatsApp Debug] phone_number field:', data.phone_number);

    const driveLink = data.drive_url
      ? `<a href="${escapeHtml(data.drive_url)}" target="_blank" rel="noopener" class="rx-download-link rx-drive-link">View on Google Drive</a>`
      : '';
    
    // Prepare WhatsApp status message (automatic sending via Twilio)
    const whatsappStatus = data.phone_number 
      ? `<div class="rx-whatsapp-status">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" style="vertical-align: middle; margin-right: 8px;">
            <path d="M10 0C4.477 0 0 4.477 0 10c0 1.89.525 3.66 1.438 5.168L.546 18.2a.75.75 0 00.954.954l3.032-.892A9.96 9.96 0 0010 20c5.523 0 10-4.477 10-10S15.523 0 10 0zm0 18a7.96 7.96 0 01-4.055-1.098l-2.293.674.674-2.293A7.96 7.96 0 012 10c0-4.411 3.589-8 8-8s8 3.589 8 8-3.589 8-8 8z" fill="#25D366"/>
            <path d="M14.5 13.5l-1.4-1.4c-.2-.2-.5-.2-.7 0l-.8.8c-.1.1-.3.1-.4 0l-2.4-2.4c-.1-.1-.1-.3 0-.4l.8-.8c.2-.2.2-.5 0-.7l-1.4-1.4c-.2-.2-.5-.2-.7 0L6 8.7c-.3.3-.3.8 0 1.1l4.2 4.2c.3.3.8.3 1.1 0l1.5-1.5c.2-.2.2-.5 0-.7z" fill="#25D366"/>
          </svg>
          <strong style="color: #25D366;">WhatsApp Sent Automatically!</strong>
          <p style="margin: 5px 0 0 28px; font-size: 13px; color: #666;">Prescription PDF has been automatically sent to ${escapeHtml(data.phone_number)} via WhatsApp.</p>
        </div>`
      : '';
    
    console.log('[WhatsApp Debug] Status message created:', whatsappStatus ? 'YES' : 'NO');
    
    generatorOutput.innerHTML = `
      <div class="medicine-card">
        <h3>✅ Visit saved and prescription generated</h3>
        <p><b>Patient:</b> ${escapeHtml(data.patient)} · ${escapeHtml(data.patient_id)}</p>
        <p><b>Visit ID:</b> ${escapeHtml(data.visit_id)}</p>
        <p><b>Doctor ID:</b> ${escapeHtml(data.doctor_id)}</p>
        <p><b>Medicines:</b> ${data.medicines.length}</p>
        <div class="rx-download-buttons">
          <a href="${escapeHtml(data.download_url)}" target="_blank" rel="noopener" class="rx-download-link">Download prescription PDF</a>
          ${driveLink}
        </div>
        ${whatsappStatus}
      </div>`;
    
    console.log('[WhatsApp Debug] DOM updated with automatic WhatsApp status');
    
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
  cachedMedicines = [];
  cachedGeneralAdvice = [];
  extractionSource = 'client';
  prescriptionTextField.dispatchEvent(new Event('input'));
  speechStatus.textContent = '';
  document.getElementById('prescriptionPatientSummary').textContent =
    `${selectedPatient.patient_name} · ${selectedPatient.patient_id} · ${selectedPatient.mobile_number}`;
  document.getElementById('prescriptionWorkflow').hidden = false;
  document.getElementById('generatorOutput').innerHTML = '';
  generateBtn.textContent = 'Save visit and generate PDF';
  generateBtn.disabled = true;
  recordSpeechBtn.disabled = false;
  
  // Clear preview
  const preview = document.getElementById('structuredPrescriptionPreview');
  if (preview) {
    preview.innerHTML = '<p class="preview-title">Structured medicine preview</p><div class="preview-empty">No medicine details detected yet. Speak or type a prescription to preview it here.</div>';
  }
  
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

if (isBrowser) {
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
}

function showError(message) {
  output.innerHTML = `<div class="error" style="background: #fee; color: #c33; padding: 15px; border-radius: 8px; margin: 10px 0;">
    ⚠️ ${message}
  </div>`;
}

function setSpeechStatus(message) {
  if (speechStatus) {
    speechStatus.textContent = message;
  }
}

function resetRecognitionState() {
  finalTranscript = '';
  interimTranscript = '';
  recognitionResultKeys = new Set();
}

function finalizeTranscriptToField() {
  const field = document.getElementById('prescriptionText');
  if (!field) return;
  field.value = normalizeTranscriptText(finalTranscript);
  field.dispatchEvent(new Event('input'));
}

function syncSpeechPreview() {
  const field = document.getElementById('prescriptionText');
  if (!field) return;
  const previewValue = buildLiveTranscript(finalTranscript, interimTranscript);
  field.value = previewValue;
  field.dispatchEvent(new Event('input'));
}

function stopMicrophoneCapture() {
  if (silenceTimer) {
    clearTimeout(silenceTimer);
    silenceTimer = null;
  }
  if (vadAnimationFrame) {
    cancelAnimationFrame(vadAnimationFrame);
    vadAnimationFrame = null;
  }
  if (micStream) {
    micStream.getTracks().forEach(track => track.stop());
    micStream = null;
  }
  if (audioContext && audioContext.state !== 'closed') {
    audioContext.close().catch(() => {});
  }
  audioContext = null;
  analyserNode = null;
  silenceStartedAt = null;
  lastAudioLevel = 0;
}

function startVADMonitor() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    setSpeechStatus('Microphone permission denied.');
    return false;
  }

  navigator.mediaDevices.getUserMedia({ audio: true })
    .then((stream) => {
      micStream = stream;
      audioContext = new (window.AudioContext || window.webkitAudioContext)();
      analyserNode = audioContext.createAnalyser();
      analyserNode.fftSize = 2048;
      analyserNode.smoothingTimeConstant = speechConfig.smoothingTimeConstant;

      const source = audioContext.createMediaStreamSource(stream);
      source.connect(analyserNode);

      let lastStatusUpdate = 0;

      function monitorAudio() {
        if (!recordingActive) {
          // Stop monitoring if recording is no longer active
          return;
        }
        
        const currentLevel = getAudioLevel(analyserNode);
        lastAudioLevel = currentLevel;

        const hasVoice = currentLevel > speechConfig.voiceThreshold;
        
        if (hasVoice) {
          // Voice detected via audio level
          lastSpeechDetectedAt = Date.now();
          hasDetectedSpeech = true;
          
          // Cancel any pending silence timer
          if (silenceTimer && recordingActive) {
            clearTimeout(silenceTimer);
            silenceTimer = null;
            silenceStartedAt = null;
            
            const now = Date.now();
            if (now - lastStatusUpdate > 500) {
              setSpeechStatus('🎤 Recording... Continue speaking.');
              lastStatusUpdate = now;
            }
          }
        }
        
        // VAD monitoring is now passive - it doesn't trigger auto-stop
        // The speech recognition API events (onspeechend) handle stopping
        
        vadAnimationFrame = requestAnimationFrame(monitorAudio);
      }

      vadAnimationFrame = requestAnimationFrame(monitorAudio);
      console.log('[VAD] Audio monitoring started');
    })
    .catch((error) => {
      console.error('[VAD] Microphone access error:', error);
      setSpeechStatus('Microphone permission denied. Please allow microphone access.');
      if (recordSpeechBtn) {
        recordSpeechBtn.textContent = 'Record Prescription';
      }
      recordingActive = false;
    });
  return true;
}

function initializeSpeechRecognition() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    setSpeechStatus('Speech recognition is not supported in this browser. Please use Chrome or Edge.');
    if (recordSpeechBtn) recordSpeechBtn.disabled = true;
    return;
  }

  recognition = new SpeechRecognition();
  recognition.lang = 'en-US';
  recognition.continuous = true; // Keep listening continuously
  recognition.interimResults = true; // Get interim results for live feedback
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    recognizing = true;
    console.log('[Recognition] Started');
    if (recordingActive) {
      setSpeechStatus('🎤 Recording... Speak naturally. Recording will finish 3 seconds after you stop speaking.');
    }
    if (recordSpeechBtn) recordSpeechBtn.textContent = 'Stop Recording';
  };

  recognition.onresult = (event) => {
    console.log('[Recognition] Result received', event);
    
    // Mark that we've received speech recognition results
    speechActivityDetected = true;
    lastSpeechDetectedAt = Date.now();
    hasDetectedSpeech = true;
    
    // Reset silence timer when new speech is recognized
    if (recordingActive && silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
      silenceStartedAt = null;
      setSpeechStatus('🎤 Recording... Continue speaking.');
    }
    
    let latestInterim = '';
    let newFinalText = '';
    
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const transcript = normalizeTranscriptText(result[0].transcript);
      if (!transcript) continue;

      if (result.isFinal) {
        // Create unique key to prevent duplicates
        const resultKey = `${recognitionSessionToken}:${index}:${transcript.toLowerCase()}`;
        if (recognitionResultKeys.has(resultKey)) {
          console.log('[Recognition] Duplicate final result, skipping:', transcript);
          continue;
        }
        recognitionResultKeys.add(resultKey);
        newFinalText = appendTranscriptSegment(newFinalText, transcript);
        console.log('[Recognition] Final result:', transcript);
      } else {
        latestInterim = transcript;
      }
    }
    
    // Accumulate final results without overwriting previous ones
    if (newFinalText) {
      finalTranscript = appendTranscriptSegment(finalTranscript, newFinalText);
      console.log('[Recognition] Accumulated final transcript length:', finalTranscript.length);
    }

    interimTranscript = latestInterim;
    
    if (finalTranscript || interimTranscript) {
      syncSpeechPreview();
    }
  };
  
  recognition.onspeechstart = () => {
    console.log('[Recognition] Speech started (onspeechstart)');
    speechActivityDetected = true;
    lastSpeechDetectedAt = Date.now();
    hasDetectedSpeech = true;
    
    // Cancel any pending silence timer
    if (silenceTimer) {
      clearTimeout(silenceTimer);
      silenceTimer = null;
      silenceStartedAt = null;
    }
    
    if (recordingActive) {
      setSpeechStatus('🎤 Recording... Continue speaking.');
    }
  };
  
  recognition.onspeechend = () => {
    console.log('[Recognition] Speech ended (onspeechend)');
    
    // Start silence timer only if recording is still active and speech has been detected
    if (recordingActive && hasDetectedSpeech && !silenceTimer) {
      silenceStartedAt = Date.now();
      setSpeechStatus('⏸️ Waiting for 3 seconds of silence...');
      
      silenceTimer = setTimeout(() => {
        console.log('[Recognition] 3 seconds of silence elapsed, auto-stopping');
        if (recordingActive) {
          stopRecording({ autoStop: true });
        }
      }, speechConfig.silenceDurationMs);
    }
  };

  recognition.onerror = (event) => {
    console.error('[Recognition] Error:', event.error);
    
    // Handle different error types
    if (event.error === 'no-speech') {
      setSpeechStatus('No speech detected. Please try again.');
    } else if (event.error === 'audio-capture') {
      setSpeechStatus('Microphone error. Please check your microphone.');
      recordingActive = false;
      stopMicrophoneCapture();
    } else if (event.error === 'not-allowed') {
      setSpeechStatus('Microphone permission denied. Please allow microphone access.');
      recordingActive = false;
      stopMicrophoneCapture();
    } else if (event.error === 'aborted') {
      // Aborted errors are usually intentional stops, ignore them
      console.log('[Recognition] Recognition aborted (normal stop)');
    } else {
      setSpeechStatus(`Speech recognition error: ${event.error}`);
    }
    
    // Don't automatically restart on critical errors
    if (['audio-capture', 'not-allowed'].includes(event.error)) {
      recordingActive = false;
      if (recordSpeechBtn) {
        recordSpeechBtn.textContent = 'Record Prescription';
        recordSpeechBtn.disabled = false;
      }
    }
  };

  recognition.onend = () => {
    console.log('[Recognition] Recognition ended, recognizing:', recognizing, 'recordingActive:', recordingActive);
    recognizing = false;
    
    // CRITICAL: Check if recording should continue
    if (recordingActive && !silenceTimer) {
      // Browser stopped recognition but doctor hasn't finished
      // Check if we should restart
      const timeSinceLastSpeech = Date.now() - (lastSpeechDetectedAt || 0);
      const shouldRestart = timeSinceLastSpeech < speechConfig.silenceDurationMs;
      
      if (shouldRestart) {
        console.log('[Recognition] Auto-restarting recognition (continuous recording)');
        setSpeechStatus('🎤 Recording... (continuing)');
        
        // Restart recognition after brief delay
        setTimeout(() => {
          if (recordingActive && recognition) {
            try {
              recognition.start();
            } catch (error) {
              console.warn('[Recognition] Restart error:', error);
              // If start fails, try again after longer delay
              setTimeout(() => {
                if (recordingActive && recognition) {
                  try {
                    recognition.start();
                  } catch (e) {
                    console.error('[Recognition] Failed to restart:', e);
                    recordingActive = false;
                    finalizeRecording();
                  }
                }
              }, 500);
            }
          }
        }, speechConfig.autoRestartDelay);
        return;
      }
    }
    
    // Recording is done
    if (!recordingActive || silenceTimer) {
      console.log('[Recognition] Recording completed, finalizing');
      finalizeRecording();
    }
  };
}

function finalizeRecording() {
  console.log('[Finalize] Finalizing recording, final transcript length:', finalTranscript.length);
  
  recordingActive = false;
  recognizing = false;
  
  // Clear any pending timers
  if (silenceTimer) {
    clearTimeout(silenceTimer);
    silenceTimer = null;
  }
  
  // Stop microphone
  stopMicrophoneCapture();
  
  // Update UI
  if (recordSpeechBtn) {
    recordSpeechBtn.textContent = 'Record Prescription';
    recordSpeechBtn.disabled = false;
  }
  
  // Process transcript
  if (finalTranscript && finalTranscript.trim()) {
    console.log('[Finalize] Processing final transcript:', finalTranscript);
    finalizeTranscriptToField();
    setSpeechStatus('✅ Recording completed. Processing prescription...');
  } else if (interimTranscript && interimTranscript.trim()) {
    // If we have interim but no final, use interim
    console.log('[Finalize] Using interim transcript:', interimTranscript);
    finalTranscript = interimTranscript;
    finalizeTranscriptToField();
    setSpeechStatus('✅ Recording completed. Processing prescription...');
  } else {
    setSpeechStatus('No speech detected. Please try recording again.');
  }
}

function startRecording() {
  console.log('[Start] Starting recording');
  
  // Set recording flag FIRST
  recordingActive = true;
  
  // Reset state
  recognitionSessionToken += 1;
  finalTranscript = '';
  interimTranscript = '';
  recognitionResultKeys = new Set();
  hasDetectedSpeech = false;
  speechActivityDetected = false;
  lastSpeechDetectedAt = null;
  silenceStartedAt = null;
  
  // Clear any pending timers
  if (silenceTimer) {
    clearTimeout(silenceTimer);
    silenceTimer = null;
  }

  if (!recognition) {
    initializeSpeechRecognition();
  }

  if (!recognition) {
    setSpeechStatus('Speech recognition could not be initialized.');
    recordingActive = false;
    return;
  }

  // Don't start if already running
  if (recognizing) {
    console.log('[Start] Already recognizing, skipping');
    return;
  }

  setSpeechStatus('🎤 Recording... Speak naturally. Recording will finish 3 seconds after you stop speaking.');

  try {
    recognition.start();
    console.log('[Start] Recognition start() called');
  } catch (error) {
    console.warn('[Start] Speech recognition start error:', error);
    // If already started, that's OK
    if (error.message && error.message.includes('already started')) {
      console.log('[Start] Recognition already started, continuing');
    } else {
      setSpeechStatus('Failed to start recording. Please try again.');
      recordingActive = false;
      return;
    }
  }

  // Start VAD monitoring for additional silence detection
  startVADMonitor();
}

function stopRecording({ autoStop = false } = {}) {
  console.log('[Stop] Stopping recording, autoStop:', autoStop);
  
  // Prevent multiple simultaneous stop calls
  if (stopRecording.inProgress) {
    console.log('[Stop] Stop already in progress');
    return;
  }
  
  if (!recordingActive && !recognizing) {
    console.log('[Stop] Not recording, nothing to stop');
    return;
  }
  
  stopRecording.inProgress = true;

  // Clear recording flag to prevent auto-restart
  recordingActive = false;

  if (autoStop) {
    setSpeechStatus('⏸️ Silence detected – stopping...');
  } else {
    setSpeechStatus('🛑 Stopping recording...');
  }
  
  // Clear any pending silence timer
  if (silenceTimer) {
    clearTimeout(silenceTimer);
    silenceTimer = null;
  }

  // Stop microphone monitoring
  stopMicrophoneCapture();

  // Stop recognition if it's running
  if (recognition && recognizing) {
    try {
      recognition.stop();
      console.log('[Stop] Recognition stop() called');
    } catch (error) {
      console.warn('[Stop] Error stopping recognition:', error);
    }
  } else {
    // If recognition already stopped, finalize immediately
    finalizeRecording();
  }

  // Reset flag after a short delay
  setTimeout(() => {
    stopRecording.inProgress = false;
  }, 500);
}

function toggleSpeechRecognition() {
  if (!recognition) {
    initializeSpeechRecognition();
  }

  // Prevent rapid clicks
  if (toggleSpeechRecognition.debounce) {
    return;
  }
  toggleSpeechRecognition.debounce = true;
  setTimeout(() => {
    toggleSpeechRecognition.debounce = false;
  }, 300);

  if (recognizing) {
    stopRecording({ autoStop: false });
    return;
  }

  startRecording();
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
  const value = String(text ?? '');
  if (typeof document === 'undefined') {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
  const div = document.createElement('div');
  div.textContent = value;
  return div.innerHTML;
}

if (isBrowser) {
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
const expiryVerificationNotice = document.getElementById('expiryVerificationNotice');
let pendingOcrExpiry = null;

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
  const status = remainingDays < 0 ? 'expired' : remainingDays <= 30 ? 'expiring' : 'valid';
  const labels = {
    en: { expired: 'Expired', expiring: 'Expiring Soon', valid: 'Valid' },
    kn: { expired: 'ಅವಧಿ ಮುಗಿದಿದೆ', expiring: 'ಶೀಘ್ರದಲ್ಲೇ ಅವಧಿ ಮುಗಿಯುತ್ತದೆ', valid: 'ಮಾನ್ಯವಾಗಿದೆ' }
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
  } catch (error) {
    staffUpdateStatus.textContent = error.message;
  }
}

function renderInventory(medicines) {
  inventoryTableBody.innerHTML = medicines.length ? medicines.map((medicine, index) => {
    const expiry = expiryPresentation(medicine.expiry_date);
    return `<tr><td>${index + 1}</td><td>${escapeHtml(medicine.medicine_name)}</td><td>${escapeHtml(medicine.strength || '')}</td><td><span>${escapeHtml(expiry.display)}</span>${expiry.status ? `<span class="expiry-status expiry-status-${expiry.status}">${escapeHtml(expiry.label)}</span>` : ''}</td><td>${escapeHtml(medicine.row_number ?? '')}</td><td>${escapeHtml(medicine.column_number ?? '')}</td></tr>`;
  }).join('') : '<tr><td colspan="6" class="table-empty">No medicines in stock.</td></tr>';
}

async function loadInventory() {
  const response = await fetch('/medicines');
  const data = await response.json();
  renderInventory(data.medicines || []);
}

function renderAlertList(element, medicines, emptyText, withExpiryStatus = false) {
  element.innerHTML = medicines.length ? medicines.map(medicine => {
    const expiry = expiryPresentation(medicine.expiry_date);
    const status = withExpiryStatus && expiry.status
      ? `<span class="expiry-status expiry-status-${expiry.status}">${escapeHtml(expiry.label)}</span>`
      : '';
    return `<div>${escapeHtml(medicine.medicine_name)} ${status}<small>(${escapeHtml(expiry.display)} | Qty: ${escapeHtml(medicine.quantity)})</small></div>`;
  }).join('') : `<div class="empty-state">${emptyText}</div>`;
}

async function loadStaffAlerts() {
  const [expiring, expired, lowStock] = await Promise.all([
    fetch('/medicines/expiring').then(response => response.json()),
    fetch('/medicines/expired').then(response => response.json()),
    fetch('/medicines/low-stock').then(response => response.json())
  ]);
  renderAlertList(expiringList, expiring.medicines || [], 'No medicines nearing expiry.', true);
  renderAlertList(expiredList, expired.medicines || [], 'No expired medicines.', true);
  renderAlertList(staffLowStockList, lowStock.medicines || [], 'No low-stock medicines.');
  document.getElementById('expiringCount').textContent = expiring.count ?? (expiring.medicines || []).length;
  document.getElementById('expiredCount').textContent = expired.count ?? (expired.medicines || []).length;
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

// ═══════════════════════════════════════════════════════════════
// WhatsApp Click-to-Chat Integration
// ═══════════════════════════════════════════════════════════════

/**
 * Normalize Indian mobile number for WhatsApp
 * Handles formats: 9876543210, +91 9876543210, 919876543210
 * Returns: 919876543210 (without + prefix for wa.me URL)
 */
function normalizePhoneForWhatsApp(phoneNumber) {
  if (!phoneNumber || typeof phoneNumber !== 'string') {
    throw new Error('Invalid phone number provided.');
  }

  // Remove all spaces, hyphens, brackets
  let cleaned = phoneNumber.trim().replace(/[\s\-\(\)]/g, '');
  
  // Remove leading + if present
  if (cleaned.startsWith('+')) {
    cleaned = cleaned.substring(1);
  }
  
  // If it already starts with 91 and has 12 digits, use as is
  if (cleaned.startsWith('91') && cleaned.length === 12) {
    return cleaned;
  }
  
  // If it's a 10-digit number, add country code 91
  if (cleaned.length === 10 && /^\d{10}$/.test(cleaned)) {
    return '91' + cleaned;
  }
  
  // If it already starts with 91, validate it has correct length
  if (cleaned.startsWith('91')) {
    const number = cleaned.substring(2);
    if (number.length === 10 && /^\d{10}$/.test(number)) {
      return cleaned;
    }
  }
  
  throw new Error('Invalid Indian mobile number. Please use a valid 10-digit number.');
}

/**
 * Generate WhatsApp Click-to-Chat URL
 */
function generateWhatsAppURL(phoneNumber, message) {
  const normalizedPhone = normalizePhoneForWhatsApp(phoneNumber);
  const encodedMessage = encodeURIComponent(message);
  return `https://wa.me/${normalizedPhone}?text=${encodedMessage}`;
}

/**
 * Get clinic name from the page or use default
 */
function getClinicName() {
  // Try to find clinic name from the page, otherwise use default
  return 'Shri XYZ Clinic';
}

/**
 * Handle WhatsApp share button click
 */
function handleWhatsAppShare(event) {
  const button = event.currentTarget;
  
  // Prevent multiple clicks
  if (button.disabled) {
    return;
  }
  
  const patientName = button.dataset.patientName;
  const phoneNumber = button.dataset.phone;
  const visitId = button.dataset.visitId;
  
  if (!phoneNumber) {
    alert('Patient mobile number is not available. Cannot send via WhatsApp.');
    return;
  }
  
  // Validate phone number before proceeding
  try {
    normalizePhoneForWhatsApp(phoneNumber);
  } catch (error) {
    alert(`Invalid phone number: ${error.message}\n\nPlease update the patient's mobile number and try again.`);
    return;
  }
  
  // Show consent confirmation dialog
  const clinicName = getClinicName();
  const consentMessage = `Before sending the prescription via WhatsApp:\n\n` +
    `Has ${patientName} agreed to receive their prescription through WhatsApp?\n\n` +
    `Note: You will need to manually download and attach the PDF in WhatsApp.`;
  
  const consent = confirm(consentMessage);
  
  if (!consent) {
    return;
  }
  
  // Prepare WhatsApp message
  const message = `Hello,\n\n` +
    `Your prescription document from ${clinicName} is ready.\n\n` +
    `Please find your prescription PDF attached to this message.\n\n` +
    `For any clarification, please contact the clinic.\n\n` +
    `Thank you.\n\n` +
    `${clinicName}`;
  
  try {
    // Generate WhatsApp URL
    const whatsappURL = generateWhatsAppURL(phoneNumber, message);
    
    // Disable button temporarily to prevent multiple clicks
    button.disabled = true;
    button.textContent = 'Opening WhatsApp...';
    
    // Open WhatsApp in new window
    // Using window.open ensures it's a user-initiated action (avoids popup blockers)
    const whatsappWindow = window.open(whatsappURL, '_blank', 'noopener,noreferrer');
    
    if (!whatsappWindow) {
      alert('Popup was blocked. Please allow popups for this site and try again.');
    }
    
    // Re-enable button after a short delay
    setTimeout(() => {
      button.disabled = false;
      button.textContent = 'Send Prescription via WhatsApp';
    }, 3000);
    
  } catch (error) {
    alert(`Failed to open WhatsApp: ${error.message}`);
    button.disabled = false;
    button.textContent = 'Send Prescription via WhatsApp';
  }
}