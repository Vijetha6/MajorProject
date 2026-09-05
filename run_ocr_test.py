

import sys
import os

sys.path.insert(0, '.')

from app import (
    resize_for_yolo,
    yolo_crop,
    extract_text_with_ocr,
    extract_with_rotations,
    clean_expiry,
    extract_generic_medicines,
    get_medicine_info_openfda,
    get_alternatives,
)
import cv2

IMG_PATH = "uploads/test_image.jpg"


def find_image():
    if not os.path.exists(IMG_PATH):
        print(f"❌ File not found: {IMG_PATH}")
        if os.path.exists("uploads"):
            print("Available files in uploads/:", os.listdir("uploads"))
        raise SystemExit(1)
    print(f"✅ Found image: {IMG_PATH}")


def safe_fetch_medicine_info(med):
    """Wrap the FDA network call so one failure doesn't kill the whole run."""
    try:
        return get_medicine_info_openfda(med)
    except Exception as e:
        print(f"   ⚠️  FDA lookup failed for '{med}': {e}")
        return {
            'uses': ['Lookup failed'],
            'side_effects': ['Lookup failed'],
            'source': 'OpenFDA (error)'
        }


def main():
    find_image()

    small = resize_for_yolo(IMG_PATH) or IMG_PATH
    print(f"📸 Using image: {small}\n")

    # ---------------- STEP 1: YOLO region detection ----------------
    print("=" * 80)
    print("STEP 1: YOLO CROP DETECTION")
    print("=" * 80)
    crops = yolo_crop(small)
    print(f"Total crops detected: {len(crops)}\n")

    raw_name_text = ""     # raw OCR text from the medicine-name region
    raw_expiry_text = ""   # raw OCR text from the expiry region
    expiry = "NOT FOUND"

    for i, c in enumerate(crops):
        label = c.get("label", "unknown")
        print(f"\n--- Crop {i}: {label.upper()} ---")

        outp = f"uploads/debug_crop_{i}_{label}.jpg"
        cv2.imwrite(outp, c["image"])
        print(f"✓ Saved: {outp}")

        if "name" in label or "medicine" in label or "drug" in label:
            text = extract_text_with_ocr(c["image"])
            if text:
                raw_name_text += " " + text
            print(f"✓ OCR text from name region: {repr(text)}")

        elif "exp" in label or "date" in label or "mfg" in label:
            text, exp = extract_with_rotations(c["image"])
            raw_expiry_text += " " + text
            print(f"✓ OCR text from expiry region: {repr(text)}")
            if exp and exp != "NOT FOUND":
                expiry = exp
                print(f"✓ Expiry parsed: {repr(exp)}")

    # ---------------- STEP 2: fallback to full image ----------------
    print("\n" + "=" * 80)
    print("STEP 2: FALLBACK OCR ON FULL IMAGE (only where crops gave nothing)")
    print("=" * 80)
    full = cv2.imread(IMG_PATH)

    if not raw_name_text.strip():
        print("No medicine-name region text found, trying full image...")
        raw_name_text = extract_text_with_ocr(full)
        print(f"Full image OCR text: {repr(raw_name_text)}")

    if expiry == "NOT FOUND":
        print("Expiry not found in crops, trying full image...")
        text, exp = extract_with_rotations(full)
        raw_expiry_text += " " + text
        print(f"Full image OCR text: {repr(text)}")
        if exp and exp != "NOT FOUND":
            expiry = exp
            print(f"Full image expiry: {repr(exp)}")

    if expiry == "NOT FOUND":
        # last resort: try cleaning whatever raw text we've gathered
        cleaned = clean_expiry(raw_name_text + " " + raw_expiry_text)
        if cleaned and cleaned != "Not found":
            expiry = cleaned
            print(f"Expiry recovered from combined text: {repr(cleaned)}")

    # ---------------- STEP 3: extract medicine name(s) from RAW text ----------------
    print("\n" + "=" * 80)
    print("STEP 3: EXTRACT MEDICINE NAME(S) FROM RAW OCR TEXT")
    print("=" * 80)
    print(f"Raw OCR text used for matching: {repr(raw_name_text)}")
    meds = extract_generic_medicines(raw_name_text)
    print(f"Detected medicines: {meds if meds else 'NONE'}")

    # ---------------- STEP 4: fetch uses / side effects / alternatives ----------------
    print("\n" + "=" * 80)
    print("STEP 4: MEDICINE INFO (uses, side effects, alternatives)")
    print("=" * 80)

    results = []

    if meds:
        for med in meds:
            print(f"\n🧾 Medicine: {med}")

            info = safe_fetch_medicine_info(med)
            alternatives = get_alternatives(med)

            print(f"   📊 Source: {info.get('source', 'OpenFDA')}")

            print("   💊 Uses:")
            for u in info['uses']:
                print(f"      - {u}")

            print("   ⚠️  Side Effects:")
            for s in info['side_effects']:
                print(f"      - {s}")

            print("   🔄 Alternatives:")
            if alternatives:
                for a in alternatives:
                    print(f"      - {a}")
            else:
                print("      (none found in database)")

            results.append({
                "medicine_name": med,
                "uses": info['uses'],
                "side_effects": info['side_effects'],
                "alternatives": alternatives,
                "source": info.get('source', 'OpenFDA'),
            })
    else:
        print("❌ No medicines detected from OCR text.")

    # ---------------- FINAL SUMMARY ----------------
    print("\n" + "=" * 80)
    print("FINAL RESULT")
    print("=" * 80)
    print(f"📅 Expiry Date: {expiry}")
    print(f"💊 Detected Medicines: {[r['medicine_name'] for r in results] if results else 'NONE'}")
    for r in results:
        print(f"\n--- {r['medicine_name'].title()} ---")
        print(f"  Uses: {r['uses']}")
        print(f"  Side Effects: {r['side_effects']}")
        print(f"  Alternatives: {r['alternatives']}")

    print("\n✅ Test complete.")


if __name__ == "__main__":
    main()