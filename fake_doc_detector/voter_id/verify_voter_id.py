import sys
import csv
from datetime import datetime
from pathlib import Path
import pandas as pd
# pyrefly: ignore [missing-import]
from playwright.sync_api import sync_playwright

# Import VoterIDDetector from our package
from .voter_id_detector import VoterIDDetector

def get_existing_processed_voters(csv_path):
    """Retrieve already verified voter IDs to support resume functionality"""
    processed = set()
    if not csv_path.exists():
        return processed
    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f, escapechar='\\')
            for row in reader:
                voter_id = row.get("VoterID")
                status = row.get("Status")
                if voter_id:
                    v_id = voter_id.strip()
                    if status and status.strip().upper() == "NOT_DONE":
                        continue
                    processed.add(v_id)
    except Exception as e:
        print(f"Error reading existing CSV {csv_path}: {e}")
    return processed

def write_voter_result(csv_path, fieldnames, data):
    """Append verified voter record to output CSV"""
    file_exists = csv_path.exists()
    try:
        with open(csv_path, 'a', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, escapechar='\\')
            if not file_exists:
                writer.writeheader()
            writer.writerow(data)
    except Exception as e:
        print(f"Error writing to CSV {csv_path}: {e}")

def main():
    excel_path = Path("data/sample_documents/voter_id/Book 2.xlsx")
    output_dir = Path("data/voter_id")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not excel_path.exists():
        print(f"Error: Excel file not found at {excel_path}")
        return 1
        
    print("Loading Excel sheets...")
    xl = pd.ExcelFile(excel_path)
    
    sheet_info = {
        'Sheet1': ('VoterIdNo', 'StateName'),
        'Rural application form': ('VoterIDCardNo', 'StateName'),
        'Assam & Meghalaya': ('VoterIDCardNo', 'StateName'),
        '15k loan applications': ('VoterIDCardNo', 'StateName'),
        'lor cum loan ': ('VoterIDCardNo', 'StateName'),
        'cc': ('VoterIdNo', 'StateName')
    }
    
    csv_fields = [
        "VoterID", "StateName_Excel", 
        "Name", "Age", "RelativeName", 
        "State", "District", "AssemblyConstituency", 
        "PollingStation", "PartName", "SerialNoInPart", 
        "Status", "Timestamp"
    ]
    
    print("Initializing VoterIDDetector check engine...")
    detector = VoterIDDetector(output_dir=output_dir)
    
    print("Launching headful Chromium browser using Playwright...")
    with sync_playwright() as p:
        try:
            # Launch visual browser
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
        except Exception as e:
            print(f"Error launching Playwright browser: {e}")
            print("Please ensure playwright is installed correctly (run: playwright install)")
            return 1
            
        try:
            for sheet_name, (voter_col, state_col) in sheet_info.items():
                if sheet_name not in xl.sheet_names:
                    print(f"Skipping sheet '{sheet_name}' (not found in workbook)")
                    continue
                    
                print(f"\n==========================================")
                print(f"PROCESSING SHEET: {sheet_name}")
                print(f"==========================================")
                
                df = xl.parse(sheet_name)
                # Find columns mapped to deal with duplicates
                orig_cols = list(df.columns)
                v_col_idx = None
                s_col_idx = None
                name_col_idx = None
                dist_col_idx = None
                
                for idx, col in enumerate(orig_cols):
                    col_name = str(col).strip()
                    base_name = col_name.split('.')[0] if '.' in col_name else col_name
                    
                    if base_name.lower() == voter_col.lower() and v_col_idx is None:
                        v_col_idx = idx
                    if base_name.lower() == state_col.lower() and s_col_idx is None:
                        s_col_idx = idx
                    if base_name.lower() in ["name", "applicantname", "nameoncard", "nameasperpan"] and name_col_idx is None:
                        name_col_idx = idx
                    if base_name.lower() in ["district", "districtname"] and dist_col_idx is None:
                        dist_col_idx = idx
                        
                if v_col_idx is None:
                    print(f"Error: Voter ID col '{voter_col}' not found in '{sheet_name}'. Skipping sheet.")
                    continue
                if s_col_idx is None:
                    print(f"Error: State name col '{state_col}' not found in '{sheet_name}'. Skipping sheet.")
                    continue
                    
                csv_name = f"verification_results_{sheet_name.strip().replace(' ', '_')}.csv"
                csv_path = output_dir / csv_name
                
                # Retrieve already processed records
                processed_voters = get_existing_processed_voters(csv_path)
                if processed_voters:
                    print(f"Loaded {len(processed_voters)} already processed voter IDs for sheet '{sheet_name}'.")
                    
                # Collect rows to process
                rows_to_process = []
                for _, row in df.iterrows():
                    voter_val = row.iloc[v_col_idx]
                    state_val = row.iloc[s_col_idx]
                    name_val = row.iloc[name_col_idx] if name_col_idx is not None else ""
                    dist_val = row.iloc[dist_col_idx] if dist_col_idx is not None else ""
                    if pd.notna(voter_val) and str(voter_val).strip() != "":
                        rows_to_process.append((
                            str(voter_val).strip(), 
                            str(state_val).strip(), 
                            str(name_val).strip() if pd.notna(name_val) else "",
                            str(dist_val).strip() if pd.notna(dist_val) else ""
                        ))
                
                total_rows = len(rows_to_process)
                print(f"Found {total_rows} valid voter ID records in sheet '{sheet_name}'.")
                
                processed_in_sheet = 0
                for idx_row, (voter_id, excel_state, excel_name, excel_dist) in enumerate(rows_to_process, 1):
                    if voter_id in processed_voters:
                        continue
                        
                    processed_in_sheet += 1
                    print(f"\nRecord {idx_row}/{total_rows} in '{sheet_name}':")
                    print(f"  Voter ID: {voter_id}")
                    print(f"  Excel State: '{excel_state}'")
                    if excel_name:
                        print(f"  Excel Name: '{excel_name}'")
                    if excel_dist:
                        print(f"  Excel District: '{excel_dist}'")
                    
                    # Run VoterIDDetector checks
                    validation_res = detector.detect(
                        voter_id=voter_id,
                        state_name=excel_state,
                        expected_name=excel_name,
                        expected_district=excel_dist,
                        page=page
                    )
                    
                    # Check for exit request
                    check_errors = [chk.get("errors", []) for chk in validation_res.get("checks", [])]
                    flat_errors = [err for sublist in check_errors for err in sublist]
                    if "Script terminated by user" in flat_errors:
                        print("Exiting runner script safely.")
                        browser.close()
                        return 0
                        
                    # If target browser page was closed, exit immediately to preserve remaining records
                    if any("context or browser has been closed" in err.lower() or "browser has been closed" in err.lower() for err in flat_errors):
                        print("Browser window was closed or disconnected. Terminating verification runner safely to preserve unprocessed records.")
                        try:
                            browser.close()
                        except Exception:
                            pass
                        return 1
                        
                    # Map result to CSV fields
                    details = validation_res.get("details", {})
                    
                    status = "Not Found" if "not registered" in "".join(validation_res.get("messages", [])).lower() else validation_res.get("overall_status")
                    if details.get("status") == "Skipped":
                        status = "Skipped"
                        
                    result_data = {
                        "VoterID": voter_id,
                        "StateName_Excel": excel_state,
                        "Name": details.get("matched_name", ""),
                        "Age": details.get("matched_age", ""),
                        "RelativeName": details.get("matched_relative_name", ""),
                        "State": details.get("matched_state", ""),
                        "District": details.get("matched_district", ""),
                        "AssemblyConstituency": details.get("matched_assembly_constituency", "") or details.get("matched_constituency", ""),
                        "PollingStation": details.get("matched_polling_station", ""),
                        "PartName": details.get("matched_part_name", ""),
                        "SerialNoInPart": details.get("matched_serial_no", ""),
                        "Status": status,
                        "Timestamp": datetime.now().isoformat()
                    }
                    
                    write_voter_result(csv_path, csv_fields, result_data)
                    
                    if status == "VALID":
                        print(f"  [SUCCESS] Verified and saved: {details.get('matched_name')} (Age: {details.get('matched_age')})")
                    else:
                        print(f"  [STATUS] Saved check result: {status} | Messages: {validation_res.get('messages')}")
                        
                if processed_in_sheet == 0:
                    print(f"Sheet '{sheet_name}' is already completely verified!")
                    
            print("\nAll Excel sheets processed completed successfully!")
            browser.close()
            return 0
            
        except KeyboardInterrupt:
            print("\nScript interrupted. Closing browser...")
            try:
                browser.close()
            except Exception:
                pass
            return 0

if __name__ == "__main__":
    sys.exit(main())
