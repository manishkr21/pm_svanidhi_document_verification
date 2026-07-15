"""Helper functions for PAN card text analysis and parsing"""

import re
from typing import Dict, List, Optional


def correct_pan_ocr_errors(cand: str) -> Optional[str]:
    """
    Correct common OCR character substitutions for a 10-character candidate.
    Returns None if uncorrectable digit/letter positions are found.
    """
    if len(cand) != 10:
        return None
        
    cand = cand.upper()
    
    digit_to_letter = {
        '0': 'O', '1': 'I', '2': 'Z', '5': 'S', '8': 'B'
    }
    letter_to_digit = {
        'O': '0', 'I': '1', 'Z': '2', 'S': '5', 'B': '8',
        'D': '0', 'L': '1', 'G': '6', 'T': '7'
    }
    
    corrected = list(cand)
    
    # Correct first 5 characters (must be letters)
    for i in range(5):
        if not corrected[i].isalpha():
            if corrected[i] in digit_to_letter:
                corrected[i] = digit_to_letter[corrected[i]]
            else:
                return None  # Uncorrectable digit in letter block
            
    # Correct next 4 characters (must be digits)
    for i in range(5, 9):
        if not corrected[i].isdigit():
            if corrected[i] in letter_to_digit:
                corrected[i] = letter_to_digit[corrected[i]]
            else:
                return None  # Uncorrectable letter in digit block
            
    # Correct last character (must be letter)
    if not corrected[9].isalpha():
        if corrected[9] in digit_to_letter:
            corrected[9] = digit_to_letter[corrected[9]]
        else:
            return None  # Uncorrectable digit in letter block
        
    res = "".join(corrected)
    if re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', res):
        return res
    return None


def find_pan_numbers_in_text_with_raw(text: str) -> List[Dict[str, str]]:
    """
    Search for PAN card numbers in OCR text with error-correction, returning both corrected and raw match.
    """
    if not text:
        return []
        
    found_exact = []
    found_nocorr = []
    found_corr = []
    
    # 1. First find exact matches
    exact_matches = re.findall(r'\b[A-Za-z]{5}[0-9]{4}[A-Za-z]\b', text)
    for m in exact_matches:
        found_exact.append({"corrected": m.upper(), "raw": m.upper()})
        
    # 2. Search for candidates of length 10 or 11 with OCR corrections
    candidates = re.findall(r'\b[A-Za-z0-9]{10,11}\b', text)
    for cand in candidates:
        cand_upper = cand.upper()
        
        # Skip standard keywords to avoid false candidates
        if any(kw in cand_upper for kw in ["INCOME", "EMAIL", "PHONE", "INDIA", "GOVT", "CARD", "ACCOUNT"]):
            continue
            
        # Try length 11 by removing one character
        if len(cand) == 11:
            for i in range(11):
                temp = cand_upper[:i] + cand_upper[i+1:]
                if re.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', temp):
                    found_nocorr.append({"corrected": temp, "raw": cand_upper})
                else:
                    corrected = correct_pan_ocr_errors(temp)
                    if corrected:
                        found_corr.append({"corrected": corrected, "raw": cand_upper})
        # Try length 10 by correcting OCR errors
        elif len(cand) == 10:
            corrected = correct_pan_ocr_errors(cand_upper)
            if corrected:
                found_corr.append({"corrected": corrected, "raw": cand_upper})
                
    # Combine preserving priority order (unique list by corrected PAN)
    all_found = []
    seen_corrected = set()
    for item in (found_exact + found_nocorr + found_corr):
        if item["corrected"] not in seen_corrected:
            all_found.append(item)
            seen_corrected.add(item["corrected"])
            
    return all_found


def find_pan_numbers_in_text(text: str) -> List[str]:
    """
    Search for PAN card numbers in OCR text with error-correction.
    Prioritizes exact matches, then candidates with 0 corrections, then corrected candidates.
    """
    return [item["corrected"] for item in find_pan_numbers_in_text_with_raw(text)]


def extract_demographics_from_text(text: str) -> dict:
    """
    Dynamically extracts PAN, Name, and DOB from selectable text or OCR text.
    Handles 'Name' label checking and multiline layouts.
    """
    info = {
        "pan": "Unknown",
        "dob": "Unknown",
        "name": "Unknown"
    }
    
    if not text:
        return info
        
    # 1. Extract PAN using robust finding with OCR error corrections
    found_pans = find_pan_numbers_in_text(text)
    if found_pans:
        info["pan"] = found_pans[0]
        
    # 2. Extract DOB (DD/MM/YYYY or DD-MM-YYYY)
    dob_match = re.search(r'\b\d{2}[/\-]\d{2}[/\-]\d{4}\b', text)
    if dob_match:
        info["dob"] = dob_match.group()
        
    # 3. Extract Name by analyzing lines
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    # Strategy A: Check lines containing the label "NAME" or "नाम" (excluding Father/Mother Name)
    for idx, line in enumerate(lines):
        line_upper = line.upper()
        if "NAME" in line_upper and "FATHER" not in line_upper and "MOTHER" not in line_upper:
            # Match characters after the label Name (handling separators like :, /, =, ])
            match = re.search(r'NAME\s*[\:\/\]\=\-]*\s*([A-Za-z\s\.\-\']+)', line, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                # Clean candidate
                candidate = re.sub(r'^[^a-zA-Z]+', '', candidate)
                candidate = re.sub(r'[^a-zA-Z]+$', '', candidate)
                if len(candidate) > 2 and not any(x in candidate.upper() for x in [
                    "INCOME", "TAX", "DEPARTMENT", "GOVT", "INDIA", "PERMANENT", "ACCOUNT", "CARD"
                ]):
                    info["name"] = candidate
                    break
            
            # If label line has no trailing name, check the next line
            if idx + 1 < len(lines):
                next_line = lines[idx + 1]
                candidate = re.sub(r'^[^a-zA-Z]+', '', next_line.strip())
                candidate = re.sub(r'[^a-zA-Z]+$', '', candidate)
                if re.match(r'^[A-Za-z\s\.\-\']+$', candidate):
                    if len(candidate) > 2 and not any(x in candidate.upper() for x in [
                        "INCOME", "TAX", "DEPARTMENT", "GOVT", "INDIA", "PERMANENT", "ACCOUNT", "CARD", "FATHER"
                    ]):
                        info["name"] = candidate
                        break
                        
    # Strategy B: Check for a line starting with Male/Female/Transgender and extract name
    if info["name"] == "Unknown":
        for line in lines:
            gender_match = re.match(r'^(Female|Male|Transgender)\s*([a-zA-Z\s\.\-\']+)', line, re.IGNORECASE)
            if gender_match:
                candidate = gender_match.group(2).strip()
                if len(candidate) > 2:
                    info["name"] = candidate
                    break
                    
    # Strategy C: Check for any uppercase/capitalized line that looks like a name
    if info["name"] == "Unknown":
        potential_names = []
        for line in lines:
            if re.match(r'^[A-Za-z\s\.\-\']+$', line):
                clean_line = line.strip()
                upper_line = clean_line.upper()
                # Skip static headers/footers
                if any(x in upper_line for x in [
                    "INCOME", "TAX", "PERMANENT", "ACCOUNT", "SIGNATURE", "CARD", "VALID", 
                    "APPLICATION", "DIGITALLY", "SIGNED", "DEPARTMENT", "GOVT", "INDIA",
                    "ELECTRONICALLY", "ISSUED", "EPAN", "RULE", "SECTION", "ACT"
                ]):
                    continue
                # Skip gender-only words
                if upper_line in ["MALE", "FEMALE", "TRANSGENDER"]:
                    continue
                if len(clean_line) > 3:
                    potential_names.append(clean_line)
                    
        if potential_names:
            # Prioritize strictly uppercase lines since actual PAN card names are in uppercase
            uppercase_names = [name for name in potential_names if name.isupper()]
            if uppercase_names:
                info["name"] = uppercase_names[0]
            else:
                info["name"] = potential_names[0]
            
    return info
