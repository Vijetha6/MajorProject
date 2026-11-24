# Manual Testing Guide - Intelligent Prescription Extraction

## How to Test

1. Start the Flask application: `python app.py`
2. Log in as a doctor
3. Select or register a patient
4. Go to "Start a new visit prescription"
5. Either:
   - Click "Record Prescription" and speak naturally
   - Type directly into the prescription text area

## Test Examples

### Example 1: Complete Natural Speech (Primary Test Case)

**What to say/type:**
```
Hello, this is a prescription recording test.

For the first medicine, prescribe Paracetamol, 500 milligrams. The patient should take one tablet in the morning and one tablet in the evening for five days. Take it after food.

For the second medicine, prescribe Cetirizine, 10 milligrams. The patient should take one tablet at bedtime for three days.

For the third medicine, prescribe Dolo, 650 milligrams. The patient should take one tablet in the morning for two days, after food.

Also, advise the patient to drink plenty of water, get adequate rest, and maintain a healthy diet.

Please make sure the medicine names, dosages, timings, and durations are recorded correctly.

That completes the prescription. Thank you.
```

**What you should see in the preview:**
- ✓ AI-powered extraction badge (green)
- 3 medicine cards
- Medicine 1: Paracetamol, 500 mg, Twice daily, Morning + Evening checked, 5 days, After food
- Medicine 2: Cetirizine, 10 mg, Once daily, Bedtime checked, 3 days
- Medicine 3: Dolo, 650 mg, Once daily, Morning checked, 2 days, After food
- General advice section with 3 items

**What should NOT appear as medicines:**
- "Hello, this is a prescription recording test"
- "Please make sure..."
- "That completes the prescription"

---

### Example 2: Very Natural Conversational Style

**What to say/type:**
```
Patient needs Paracetamol 500. Give one tablet after breakfast and another after dinner. Continue this for five days.
```

**Expected result:**
- Medicine: Paracetamol
- Dosage: 500 mg
- Frequency: Twice daily
- Timing: Morning, Evening
- Duration: 5 days
- Food: After food

---

### Example 3: Compact Prescription

**What to say/type:**
```
Give Paracetamol 500 mg morning and night for five days after meals.
```

**Expected result:**
- Medicine: Paracetamol
- Dosage: 500 mg
- Frequency: Twice daily
- Timing: Morning, Evening
- Duration: 5 days
- Food: After food

---

### Example 4: Bedtime Medication

**What to say/type:**
```
Cetirizine ten milligrams at bedtime for three days.
```

**Expected result:**
- Medicine: Cetirizine
- Dosage: 10 mg
- Frequency: Once daily
- Timing: Bedtime
- Duration: 3 days

---

### Example 5: Multiple Medicines in One Paragraph

**What to say/type:**
```
Start with Paracetamol 500 mg twice daily for five days. Also give Cetirizine 10 mg at night for three days.
```

**Expected result:**
- 2 medicine cards
- Medicine 1: Paracetamol, 500 mg, Twice daily, 5 days
- Medicine 2: Cetirizine, 10 mg, Once daily, Bedtime, 3 days

---

### Example 6: Correction During Speech

**What to say/type:**
```
Prescribe Paracetamol 500 mg twice daily for five days. Actually, make that three days.
```

**Expected result:**
- Medicine: Paracetamol
- Dosage: 500 mg
- Frequency: Twice daily
- Duration: **3 days** (corrected value, not 5 days)

---

### Example 7: Minimal Information (Safety Check)

**What to say/type:**
```
Paracetamol 500 mg.
```

**Expected result:**
- Medicine: Paracetamol
- Dosage: 500 mg
- Frequency: As directed (NOT invented)
- Duration: As directed (NOT invented)
- ⚠ Yellow highlighting on frequency/duration fields

---

### Example 8: General Advice Only (Should Not Create Medicine)

**What to say/type:**
```
Please tell the patient to drink plenty of water, get adequate rest, and avoid spicy food.
```

**Expected result:**
- **0 medicine cards**
- General advice section with 3 items
- No medicines extracted

---

### Example 9: Mixed Medicines and Advice

**What to say/type:**
```
Give Paracetamol 500 mg twice daily for five days. Also tell the patient to drink lots of water and take rest.
```

**Expected result:**
- 1 medicine card: Paracetamol
- General advice section with: "Drink lots of water" and "Take rest"

---

### Example 10: Context Across Many Sentences

**What to say/type:**
```
First, prescribe Paracetamol. The dosage should be 500 milligrams. The patient needs to take it in the morning. Also in the evening. This should continue for five days. Make sure they take it after eating food.
```

**Expected result:**
- **1 medicine card** (all sentences refer to same medicine)
- Medicine: Paracetamol
- Dosage: 500 mg
- Timing: Morning, Evening
- Duration: 5 days
- Food: After food

---

## What to Check in the UI

### Extraction Indicator
- **✓ AI-powered extraction** (green badge) = Gemini is working
- **⚠ Pattern-based fallback** (yellow badge) = Gemini unavailable, using regex fallback
- **Client-side parsing** (blue badge) = JavaScript-only extraction

### Field Warnings
- Missing medicine name → Red border
- Missing/uncertain dosage → Yellow border
- Should highlight before you can save

### Interactive Features
1. **Edit any field**: Click and type to modify
2. **Change frequency**: Use dropdown
3. **Toggle timing**: Check/uncheck boxes
4. **Add medicine**: Click "Add Medicine" button → blank card appears
5. **Remove medicine**: Click × on medicine card OR "Remove Medicine" button
6. **Save**: Click "Save visit and generate PDF"

### What Happens After Save
1. Loading indicator appears
2. Visit saved confirmation shows
3. PDF download link appears
4. Google Drive link (if configured)
5. Patient history updates with new visit
6. Can view generated PDF

---

## Troubleshooting

### If extraction shows "Pattern-based fallback"
- Check `.env` file has `GEMINI_API_KEY`
- Check internet connection
- Check Gemini API quota/limits
- System still works, just uses simpler extraction

### If no medicines detected
- Check if text actually contains medicine names
- Try adding dosage (e.g., "500 mg")
- Try being more explicit: "Prescribe Paracetamol..."
- Check if it's only general advice (correct behavior)

### If too many medicines detected
- Check for repeated medicine names
- AI should deduplicate, but you can remove extras manually
- Click × button on unwanted medicine cards

### If wrong information extracted
- All fields are editable
- Click on field and correct it
- System requires your review before saving

---

## Medical Safety Reminders

✅ **The system will NEVER:**
- Invent medicine names
- Guess dosages
- Assume durations
- Auto-fill missing critical information
- Save without your review

✅ **You MUST:**
- Review every extracted field
- Confirm medicine names are correct
- Verify dosages are accurate
- Check durations are appropriate
- Manually add missing information

⚠️ **Always verify extracted data before saving.**

---

## Quick Verification Checklist

After typing/recording a prescription:

- [ ] Wait 1.5 seconds for extraction to complete
- [ ] Check extraction indicator (green = AI working)
- [ ] Count medicine cards (should match expected)
- [ ] Review each medicine name
- [ ] Verify each dosage
- [ ] Check timing checkboxes
- [ ] Confirm food instructions
- [ ] Review general advice (if any)
- [ ] Edit any incorrect fields
- [ ] Click "Save visit and generate PDF"
- [ ] Download and verify PDF content

---

## Example PDFs to Check

After saving, verify the generated PDF contains:
- Patient information (name, age, gender, mobile)
- Doctor information and Visit ID
- Medicine table with all prescribed medicines
- Proper M-A-E-B (Morning-Afternoon-Evening-Bedtime) format
- Food instructions under each medicine (if specified)
- Digital signature
- QR code for download
- Professional formatting

---

## Support

If something doesn't work as expected:
1. Check browser console for JavaScript errors
2. Check Flask terminal for backend errors
3. Verify `.env` configuration
4. Try fallback: Type manually and use client-side extraction
5. Review `INTELLIGENT_EXTRACTION_IMPLEMENTATION.md` for details
