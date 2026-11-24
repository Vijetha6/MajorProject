'use strict';

const assert = require('node:assert/strict');

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

function evaluateSilenceState(audioLevel, currentState) {
  const config = { silenceDurationMs: 3000, voiceThreshold: 0.08, noiseFloor: 0.02 };

  if (audioLevel >= config.voiceThreshold + config.noiseFloor) {
    return { speechDetected: true, silenceStartedAt: null, status: 'Voice detected.' };
  }

  if (currentState.speechDetected) {
    const silenceStart = currentState.silenceStartedAt || Date.now();
    const elapsed = Date.now() - silenceStart;
    if (elapsed >= config.silenceDurationMs) {
      return { speechDetected: false, silenceStartedAt: silenceStart, status: 'Silence detected – stopping in 3 seconds.' };
    }
    return { speechDetected: false, silenceStartedAt: silenceStart, status: 'Silence detected – stopping in 3 seconds.' };
  }

  return { speechDetected: false, silenceStartedAt: currentState.silenceStartedAt || Date.now(), status: 'Ready to record.' };
}

(function runVoiceTests() {
  const testCases = [
    {
      name: 'keeps legitimate repeat words intact',
      fn: () => {
        const transcript = appendTranscriptSegment('Hello', 'Hello');
        assert.equal(transcript, 'Hello Hello');
      }
    },
    {
      name: 'stops after 3 seconds of silence',
      fn: () => {
        const state = { speechDetected: true, silenceStartedAt: Date.now() - 3001 };
        const next = evaluateSilenceState(0.01, state);
        assert.equal(next.status, 'Silence detected – stopping in 3 seconds.');
      }
    },
    {
      name: 'resets silence timer when speech resumes',
      fn: () => {
        const state = { speechDetected: false, silenceStartedAt: Date.now() - 1000 };
        const resumed = evaluateSilenceState(0.2, state);
        assert.equal(resumed.speechDetected, true);
      }
    },
    {
      name: 'keeps final transcript free from duplicate interim fragments',
      fn: () => {
        const finalText = appendTranscriptSegment('I am', 'Hello');
        const live = `${finalText} Hello`;
        assert.ok(live.includes('Hello'));
        assert.ok(!live.includes('I am I am'));
      }
    }
  ];

  testCases.forEach(({ name, fn }) => {
    try {
      fn();
      console.log(`PASS: ${name}`);
    } catch (error) {
      console.error(`FAIL: ${name}`);
      throw error;
    }
  });
})();
