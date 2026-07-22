"""Voter ID verification and check engine using Playwright and EasyOCR"""

import re
import logging
import base64
from pathlib import Path
from typing import Dict, List, Optional
# pyrefly: ignore [missing-import]
import easyocr

logger = logging.getLogger(__name__)



class VoterIDDetector:
    """
    Comprehensive Voter ID (EPIC) detector and checker.
    
    Validates Voter ID using:
    1. Format checks (e.g., standard regex patterns like 3 letters followed by 7 digits)
    2. Real-time ECI Electoral Roll verification via Playwright browser automation
    3. Automated CAPTCHA solving using EasyOCR
    """
    
    # Standard format: 3 letters, 7 digits
    VOTER_ID_PATTERN = re.compile(r'^[A-Z]{3}[0-9]{7}$')

    def __init__(self, output_dir: Optional[str] = None):
        """Initialize the Voter ID Detector"""
        self.output_dir = Path(output_dir) if output_dir else Path("data/voter_id")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.reader = easyocr.Reader(['en'], gpu=False)
        logger.info("VoterIDDetector initialized with EasyOCR reader")

    def validate_basic_format(self, voter_id: str) -> Dict:
        """
        Validate basic EPIC / Voter ID number format.
        """
        result = {
            "check_name": "Basic Format Validation",
            "passed": False,
            "errors": [],
            "details": {}
        }
        
        if not voter_id:
            result["errors"].append("Voter ID / EPIC number is empty")
            return result
            
        cleaned = str(voter_id).strip().upper()
        result["details"]["cleaned_voter_id"] = cleaned
        
        # Check standard format
        if not self.VOTER_ID_PATTERN.match(cleaned):
            result["errors"].append(
                f"Voter ID format mismatch. Expected 3 letters followed by 7 digits, got: '{cleaned}'"
            )
            return result
            
        result["passed"] = True
        result["details"]["format"] = "valid"
        return result



    def solve_captcha(self, img_bytes: bytes) -> str:
        """
        Solve CAPTCHA using EasyOCR after applying optimized in-memory preprocessing.
        """
        try:
            import cv2
            import numpy as np
            
            # Load image from bytes in-memory using OpenCV
            nparr = np.frombuffer(img_bytes, np.uint8)
            img_cv = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img_cv is None:
                logger.error("Failed to decode CAPTCHA image bytes via OpenCV")
                return ""
                
            # 1. Median filter to remove thin diagonal/horizontal lines
            denoised = cv2.medianBlur(img_cv, 3)
            # 2. Convert to grayscale
            gray = cv2.cvtColor(denoised, cv2.COLOR_BGR2GRAY)
            # 3. Clamp background to white
            gray[gray > 135] = 255
            # 4. Clamp text to black
            gray[gray < 95] = 0
            # 5. Resize to 3x using cubic interpolation
            resized = cv2.resize(gray, (0, 0), fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
            # 6. Smooth edges slightly
            blurred = cv2.GaussianBlur(resized, (3, 3), 0)
            
            # Run EasyOCR with alphanumeric allowlist directly on the in-memory numpy array
            alphanumeric = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
            results = self.reader.readtext(blurred, detail=0, allowlist=alphanumeric)
            cleaned = "".join(results).strip().replace(" ", "")
            logger.info(f"EasyOCR solved CAPTCHA as: '{cleaned}'")
            return cleaned
        except Exception as e:
            logger.error(f"Error solving CAPTCHA with EasyOCR: {e}")
            return ""

    def verify_electoral_roll(self, voter_id: str, state_name: str, page) -> Dict:
        """
        Interacts with the ECI website via Playwright to fetch voter registration details.
        
        Requires a Playwright Page instance.
        """
        result = {
            "check_name": "Electoral Roll Online Verification",
            "passed": False,
            "errors": [],
            "details": {}
        }
        
        try:
            # Navigate to ECI search portal
            page.goto("https://electoralsearch.eci.gov.in/")
            page.wait_for_timeout(2000)
            
            # Hide Toastify notification overlay to prevent any pointer interception errors
            try:
                page.add_style_tag(content=".Toastify { display: none !important; }")
            except Exception:
                pass
            
            # Click the Search by EPIC tab
            page.locator("button#epic").click()
            page.wait_for_timeout(1000)
            
            # Fill EPIC ID
            page.locator("input#epicID").fill(voter_id)
            
            # Locate and select State dropdown
            # Check by aria-label or tag name
            state_select = page.locator('select[aria-label="Select State"]')
            if not state_select.count():
                # Fallback to second select
                state_select = page.locator('select').nth(1)
                
            # Retrieve all option values and text content dynamically from the dropdown
            options = state_select.evaluate(
                "el => Array.from(el.options).map(opt => ({value: opt.value, label: opt.textContent.trim()}))"
            )

            # Match state_name against options
            def normalize(s: str) -> str:
                s = str(s).strip().lower()
                s = " ".join(s.split())
                s = s.replace(" & ", " and ")
                return s

            norm_state = normalize(state_name)
            selected_value = None

            # First look for exact match of normalized label
            for opt in options:
                if normalize(opt["label"]) == norm_state:
                    selected_value = opt["value"]
                    break

            # If not found, look for substring match
            if not selected_value:
                for opt in options:
                    norm_label = normalize(opt["label"])
                    if norm_state in norm_label or norm_label in norm_state:
                        selected_value = opt["value"]
                        break

            if selected_value:
                state_select.select_option(value=selected_value)
            else:
                # Fallback directly to selecting by label
                try:
                    state_select.select_option(label=state_name)
                except Exception:
                    result["errors"].append(f"Could not find a matching state option for '{state_name}' in the dropdown.")
                    return result
            page.wait_for_timeout(1000)
            
            scraped_ok = False
            attempts = 0
            max_attempts = 10
            last_captcha_src = ""
            
            while not scraped_ok and attempts < max_attempts:
                attempts += 1
                logger.info(f"Attempting to capture and solve CAPTCHA (attempt {attempts}/{max_attempts})...")
                
                # Close any Toastify error toast if present to prevent it blocking interactions
                try:
                    toast_close = page.locator('button.Toastify__close-button')
                    if toast_close.count() > 0:
                        toast_close.first.click()
                        page.wait_for_timeout(300)
                except Exception as t_err:
                    logger.debug(f"Failed to close Toastify toast: {t_err}")
                
                # Wait for a NEW Captcha image to load
                captcha_loaded = False
                captcha_src = ""
                for _ in range(90): # up to 45 seconds
                    captcha_img = page.locator('img[width="190"]')
                    if captcha_img.count() > 0:
                        src = captcha_img.get_attribute("src")
                        if src and "undefined" not in src and len(src) > 100 and src != last_captcha_src:
                            captcha_src = src
                            captcha_loaded = True
                            break
                    page.wait_for_timeout(500)
                    
                if not captcha_loaded:
                    # Fallback to current src if different not found but loaded
                    captcha_img = page.locator('img[width="190"]')
                    if captcha_img.count() > 0:
                        src = captcha_img.get_attribute("src")
                        if src and "undefined" not in src and len(src) > 100:
                            captcha_src = src
                            captcha_loaded = True
                            
                if not captcha_loaded:
                    result["errors"].append("ECI CAPTCHA image failed to load in time.")
                    return result
                
                last_captcha_src = captcha_src
                
                # Decode CAPTCHA image
                base64_data = re.sub('^data:image/.+;base64,', '', captcha_src)
                base64_data = "".join(base64_data.split())
                missing_padding = len(base64_data) % 4
                if missing_padding:
                    base64_data += '=' * (4 - missing_padding)
                    
                try:
                    img_data = base64.b64decode(base64_data)
                except Exception as b64_err:
                    logger.error(f"Failed to decode base64 CAPTCHA: {b64_err}")
                    result["errors"].append("Base64 CAPTCHA decoding failed.")
                    return result
                
                # Auto-solve in-memory
                solved_captcha = self.solve_captcha(img_data)
                
                # Fill the solved CAPTCHA in browser
                page.locator('input[name="captcha"]').fill(solved_captcha)
                
                # Save screenshot
                screenshot_path = self.output_dir / "screenshot.png"
                try:
                    page.screenshot(path=str(screenshot_path))
                except Exception as s_err:
                    logger.error(f"Failed to save browser screenshot: {s_err}")
                
                # Click SEARCH
                search_btn = page.locator('button.btn-active:has-text("SEARCH")')
                if search_btn.count() == 0:
                    search_btn = page.locator('button:has-text("SEARCH")')
                
                if search_btn.count() > 0:
                    search_btn.click()
                else:
                    page.locator('input[name="captcha"]').press("Enter")
                
                # Wait for 1 second to allow ECI API submission and page update, avoiding race conditions with old state
                page.wait_for_timeout(1000)
                
                # Wait for search results or captcha errors
                results_state = "none"
                for _ in range(16): # Wait up to 8 seconds
                    table_count = page.locator("table").count()
                    if table_count > 0:
                        rows_count = page.locator("table tr").count()
                        if rows_count > 1:
                            results_state = "found"
                            break
                            
                    page_src = page.content()
                    lower_src = page_src.lower()
                    if "no record found" in lower_src or "कोई रिकॉर्ड नहीं मिला" in lower_src or "no result found" in lower_src:
                        results_state = "not_found"
                        break
                        
                    # Check for captcha invalid errors
                    if "captcha" in lower_src and ("invalid" in lower_src or "error" in lower_src or "गलत" in lower_src or "दर्ज" in lower_src):
                        results_state = "captcha_error"
                        break
                        
                    page.wait_for_timeout(500)
                
                if results_state == "found":
                    # Successfully loaded results table
                    table_rows = page.locator("table tr").all()
                    cells = [td.text_content() for td in table_rows[1].locator("td").all()]
                    cells = [str(c).strip() for c in cells]
                    
                    if len(cells) >= 12:
                        result["passed"] = True
                        result["details"] = {
                            "voter_id": voter_id,
                            "matched_name": cells[2].split('\n')[0].strip(),
                            "matched_age": cells[3].strip(),
                            "matched_relative_name": cells[4].split('\n')[0].strip(),
                            "matched_state": cells[5].strip(),
                            "matched_district": cells[6].strip(),
                            "matched_assembly_constituency": cells[7].strip(),
                            "matched_parliamentary_constituency": cells[8].strip(),
                            "matched_polling_station": cells[9].strip(),
                            "matched_part_name": cells[10].strip(),
                            "matched_serial_no": cells[11].strip(),
                            "status": "Found"
                        }
                        scraped_ok = True
                    elif len(cells) >= 11:
                        result["passed"] = True
                        result["details"] = {
                            "voter_id": voter_id,
                            "matched_name": cells[2].split('\n')[0].strip(),
                            "matched_age": cells[3].strip(),
                            "matched_relative_name": cells[4].split('\n')[0].strip(),
                            "matched_state": cells[5].strip(),
                            "matched_district": cells[6].strip(),
                            "matched_assembly_constituency": cells[7].strip(),
                            "matched_parliamentary_constituency": cells[7].strip(),
                            "matched_polling_station": cells[8].strip(),
                            "matched_part_name": cells[9].strip(),
                            "matched_serial_no": cells[10].strip(),
                            "status": "Found"
                        }
                        scraped_ok = True
                    else:
                        result["errors"].append(f"Unexpected columns count in results: {len(cells)}")
                        scraped_ok = True
                        
                elif results_state == "not_found":
                    result["errors"].append("Voter ID not registered in ECI Electoral Roll.")
                    result["details"]["status"] = "Not Found"
                    scraped_ok = True
                    
                else:
                    # Timeout / CAPTCHA failure
                    logger.warning("Search failed or invalid CAPTCHA. Refreshing captcha image and retrying...")
                    # Click refresh captcha button to fetch a new captcha
                    try:
                        refresh_btn = page.locator('img[width="190"] ~ svg').first
                        if refresh_btn.count() > 0:
                            refresh_btn.click()
                            page.wait_for_timeout(1000)
                    except Exception:
                        pass
                        
            if not scraped_ok:
                result["errors"].append("Maximum attempts reached without resolving search results.")
                
        except Exception as ex:
            logger.error(f"Error during Electoral Roll check: {ex}")
            result["errors"].append(f"Automation error: {ex}")
            
        return result

    def detect(self, voter_id: str, state_name: str, page, expected_name: str = None, expected_district: str = None) -> Dict:
        """
        Complete check function matching PAN / Aadhaar structure.
        """
        logger.info(f"Starting Voter ID verification for EPIC: {voter_id}")
        
        results = {
            "voter_id": voter_id.strip().upper(),
            "is_fake": False,
            "confidence": 0.0,
            "checks": [],
            "overall_status": "VALID",
            "messages": []
        }
        
        # Check 1: Format Checks
        format_res = self.validate_basic_format(voter_id)
        results["checks"].append(format_res)
        
        if not format_res["passed"]:
            results["overall_status"] = "INVALID"
            results["is_fake"] = True
            results["messages"].extend(format_res["errors"])
            return results
            
        # Check 2: Electoral Database Checks via Playwright page
        electoral_res = self.verify_electoral_roll(voter_id, state_name, page)
        results["checks"].append(electoral_res)
        
        if electoral_res["passed"]:
            results["confidence"] = 1.0
            results["overall_status"] = "VALID"
            results["messages"].append("Voter ID successfully verified against ECI online records.")
            results["details"] = electoral_res["details"]
            
            mismatches = []
            
            def verify_contained_match(val1: str, val2: str) -> bool:
                if not val1 or not val2:
                    return False
                def clean_val(n):
                    first_line = str(n).split('\n')[0]
                    # Keep alphanumeric characters and spaces, lowercase
                    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', first_line).lower().strip()
                    # Remove common titles
                    for title in ["mr", "mrs", "ms", "late", "shri", "smt"]:
                        cleaned = re.sub(rf'\b{title}\b', '', cleaned)
                    return " ".join(cleaned.split())
                
                c1 = clean_val(val1)
                c2 = clean_val(val2)
                
                if not c1 or not c2:
                    return False
                    
                return c1 in c2 or c2 in c1

            # Robust applicant name matching
            if expected_name:
                matched_name = electoral_res["details"].get("matched_name", "")
                if not verify_contained_match(expected_name, matched_name):
                    mismatches.append(f"Name mismatch: Excel name '{expected_name}' is not contained in ECI matched name '{matched_name}'")
                    
            # Parliamentary Constituency matching vs Excel district column
            if expected_district:
                matched_pc = electoral_res["details"].get("matched_parliamentary_constituency", "")
                if not verify_contained_match(expected_district, matched_pc):
                    mismatches.append(f"Constituency mismatch: Excel district '{expected_district}' is not contained in ECI matched Parliamentary Constituency '{matched_pc}'")
                    
            if mismatches:
                results["overall_status"] = "POTENTIALLY_FAKE"
                results["is_fake"] = True
                results["confidence"] = 0.95
                results["messages"] = mismatches
                results["details"] = electoral_res["details"]
        else:
            # Check if this failure is because the ID is not found (unregistered) or because it's "not done" (e.g. CAPTCHA/Automation error)
            is_not_found = any("not registered" in str(err).lower() for err in electoral_res.get("errors", [])) or electoral_res.get("details", {}).get("status") == "Not Found"
            
            if is_not_found:
                results["overall_status"] = "POTENTIALLY_FAKE"
                results["is_fake"] = True
                results["confidence"] = 0.95
            else:
                results["overall_status"] = "NOT_DONE"
                results["is_fake"] = False
                results["confidence"] = 0.0
                
            results["messages"].extend(electoral_res["errors"])
            if "status" in electoral_res.get("details", {}):
                results["details"] = electoral_res["details"]
                
        return results
