import os
import re
import shutil
from PIL import Image, ImageOps
import pytesseract

# Configure tesseract binary if available in standard macOS / Linux locations
if not shutil.which("tesseract"):
    for path in [
        "/opt/homebrew/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/usr/bin/tesseract",
        "/opt/local/bin/tesseract",
    ]:
        if os.path.exists(path):
            pytesseract.pytesseract.tesseract_cmd = path
            break


def clean_medicine_line(line: str) -> str:
    """Clean a prescription medicine line to extract the medicine name and dosage."""
    # Remove leading bullets, numbering, or list markers
    s = re.sub(r"^[\s\d.\-*•)]+", "", line.strip())
    # Remove dosage form prefixes like Tab., Cap., etc.
    s = re.sub(r"^(?:tab(?:let)?\.?|cap(?:sule)?\.?)\s*", "", s, flags=re.IGNORECASE)
    # Remove trailing frequency and duration instructions (e.g., BD x5 days, OD)
    s = re.sub(
        r"\s+(?:bd|od|tds|qid|tid|hs|sos|x\s*\d+\s*days?|\d+\s*days?|once\s+daily|twice\s+daily).*$",
        "",
        s,
        flags=re.IGNORECASE,
    )
    return s.strip() if s.strip() else line.strip()


def extract_prescription_data(image_path: str) -> dict:
    """
    Extracts raw OCR text from a prescription image and parses structured
    information (medicine lines and prescription date) using regex.
    Gracefully handles blurry or unreadable scans without raising exceptions.
    """
    raw_text = ""
    try:
        if os.path.exists(image_path):
            image = Image.open(image_path)
            # Correct phone/camera EXIF rotation if present
            image = ImageOps.exif_transpose(image)
            raw_text = pytesseract.image_to_string(image)
    except Exception:
        raw_text = ""

    medicines = []
    date = None

    # Dosage pattern: numbers followed by mg, or words like tablet, syrup, BD, OD
    dosage_pattern = re.compile(
        r"(\d+\s*mg|\b(?:tablet|tab|syrup|syr|bd|od)\b)", re.IGNORECASE
    )
    # Date pattern: dd/mm/yyyy, dd-mm-yyyy, or dd.mm.yyyy
    date_pattern = re.compile(r"\b(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})\b")

    if raw_text:
        lines = raw_text.splitlines()
        for line in lines:
            trimmed = line.strip()
            if not trimmed:
                continue

            # Check for date pattern
            if not date:
                date_match = date_pattern.search(trimmed)
                if date_match:
                    date = date_match.group(1)

            # Check for medicine pattern
            if dosage_pattern.search(trimmed):
                med = clean_medicine_line(trimmed)
                if med and med not in medicines:
                    medicines.append(med)

    return {
        "raw_text": raw_text or "No text detected",
        "structured": {
            "medicines": medicines or [],
            "date": date or "Not found",
        },
    }
