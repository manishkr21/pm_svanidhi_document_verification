"""
verifier.py

Document verification module for matching extracted document attributes against
ground truth JSON files (e.g. source/<person_id>.json).

Rules:
- Matched attributes add to the score.
- Missing attributes are not penalized.
- Mismatched attributes are flagged and subtract from the score.
- Calculates an overall confidence score percentage.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Set

from config import logger, BASE_DIR


def normalize_key(key: str) -> str:
    """Normalizes field keys for matching (lowercase, strip non-alphanumeric chars)."""
    return re.sub(r"[^a-z0-9]", "", key.lower())


def normalize_value(val: Any) -> str:
    """Normalizes field values for string comparison."""
    if val is None:
        return ""
    val_str = str(val).strip().lower()
    # Normalize common date formats or separators (e.g. 20/08/2024 vs 20-08-2024)
    val_str = re.sub(r"[\s\-\.\:\,/]+", "", val_str)
    return val_str


def token_similarity(str1: str, str2: str) -> float:
    """
    Calculates token overlap ratio between two strings (0.0 to 1.0).
    Prevents false mismatches due to minor formatting, punctuation, or word order variations.
    """
    tokens1 = set(re.findall(r"[a-z0-9]+", str1.lower()))
    tokens2 = set(re.findall(r"[a-z0-9]+", str2.lower()))

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1.intersection(tokens2)
    smaller_size = min(len(tokens1), len(tokens2))
    union_size = len(tokens1.union(tokens2))

    overlap_ratio = len(intersection) / smaller_size
    jaccard_ratio = len(intersection) / union_size

    return max(overlap_ratio, jaccard_ratio)


# Generic extracted keys that should never be loosely matched to compound ground truth keys
GENERIC_KEYS: Set[str] = {
    "name", "no", "id", "code", "type", "date", "amount", "status", "number", "card", "location", "address"
}


# Key aliases to map common extracted fields to ground truth source fields
KEY_ALIASES: Dict[str, List[str]] = {
    "applicantname": ["applicant_name", "holder_name", "person_name", "name", "full_name"],
    "fatherorspousename": ["father_name", "spouse_name", "father_or_spouse_name", "husband_name"],
    "pannumber": ["pan", "pan_no", "pan_number", "pan_card_number"],
    "aadhaartoken": ["aadhaar", "aadhaar_no", "aadhaar_number", "aadhaar_card_number", "uid", "aadhaar_token"],
    "voteridcardno": ["voter_id", "voter_card_no", "voter_id_number", "epic_no", "voter_id_card_no"],
    "dateofbirth": ["dob", "date_of_birth", "birth_date"],
    "gendername": ["gender", "sex", "gender_name"],
    "mobileno": ["mobile", "mobile_number", "phone", "phone_number", "contact_no", "mobile_no"],
    "aadhaaraddress": ["aadhaar_address", "permanent_address", "address"],
    "currentaddress": ["current_address", "present_address", "residence_address"],
    "papin": ["pincode", "pin_code", "pin", "postal_code", "pa_pin"],
    "loanamountrequired": ["loan_amount", "requested_loan_amount", "loan_amount_required"],
    "loantenure": ["tenure", "loan_tenure", "tenure_months"],
    "preferredbank": ["bank_name", "bank", "preferred_bank"],
    "categoryname": ["category", "category_name", "category_type"],
    "familydetailsname": ["family_details_name", "family_name", "guardian_name", "relative_name"],
    "activityname": ["activity", "activity_name", "vending_activity", "business_activity"],
    "placeofvendingname": ["place_of_vending", "place_of_vending_name", "vending_place", "vending_location"],
    "statename": ["state", "state_name"],
    "districtname": ["district", "district_name"],
    "paymentaggregatorname": ["payment_aggregator_name", "payment_aggregator", "payment_bank", "payment_aggregator_id"],
    "stationaryvendorlocation": ["stationary_vendor_location", "vendor_location", "vending_address"],
    "lorno": ["lor_no", "lor_number", "letter_of_recommendation_no"],
    "durationofvending": ["duration_of_vending", "vending_duration"],
    "applicationno": ["application_no", "application_number", "app_no"],
    "applicationdate": ["application_date", "app_date"],
    "voteridcardno": ["voter_id", "voter_card_no", "voter_id_number", "epic_no", "voter_id_card_no"]
}


class DocumentVerifier:
    """Verifies extracted document fields against ground truth source JSON."""

    def __init__(self, source_dir: Optional[Path] = None):
        self.source_dir = source_dir or (BASE_DIR / "source")

    def load_source_json(self, person_id: str) -> Dict[str, Any]:
        """
        Loads ground truth JSON file for a given person_id (e.g., person1 -> source/person1.json).
        """
        person_name = Path(person_id).stem
        json_path = self.source_dir / f"{person_name}.json"

        if not json_path.exists():
            if Path(person_id).exists():
                json_path = Path(person_id)
            else:
                raise FileNotFoundError(f"Source JSON file not found at '{json_path}'")

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.error("Failed to read source JSON '%s': %s", json_path, e)
            raise ValueError(f"Failed to read source JSON: {str(e)}")

    def _flatten_data(self, data: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
        """Flattens nested dictionaries into single-level key-value mapping."""
        flattened = {}
        for k, v in data.items():
            key_name = f"{prefix}_{k}" if prefix else str(k)
            if isinstance(v, dict):
                flattened.update(self._flatten_data(v, key_name))
            elif isinstance(v, list):
                str_items = [str(item) for item in v if item is not None]
                flattened[key_name] = ", ".join(str_items)
            else:
                flattened[key_name] = v
        return flattened

    def _find_matching_extracted_value(
        self, norm_gt_key: str, extracted_flat: Dict[str, Any]
    ) -> Tuple[Optional[str], Optional[Any]]:
        """
        Finds extracted key and value matching a normalized ground truth key.
        Checks exact key match, alias key match, or precise sub-key match.
        Prevents generic extracted keys (like 'name') from matching unrelated compound keys.
        """
        # 1. Direct normalized key match
        for ext_key, ext_val in extracted_flat.items():
            norm_ext_key = normalize_key(ext_key)
            if norm_ext_key == norm_gt_key:
                return ext_key, ext_val

        # 2. Check alias mapping
        aliases = KEY_ALIASES.get(norm_gt_key, [])
        norm_aliases = [normalize_key(a) for a in aliases]
        for ext_key, ext_val in extracted_flat.items():
            norm_ext_key = normalize_key(ext_key)
            if norm_ext_key in norm_aliases:
                return ext_key, ext_val

        # 3. Specific compound suffix match (excluding generic keys like 'name')
        for ext_key, ext_val in extracted_flat.items():
            norm_ext_key = normalize_key(ext_key)
            if norm_ext_key in GENERIC_KEYS:
                continue  # Do not match generic keys to compound ground truth keys via endswith

            if len(norm_ext_key) >= 6 and len(norm_gt_key) >= 6:
                if norm_gt_key.endswith(norm_ext_key) or norm_ext_key.endswith(norm_gt_key):
                    return ext_key, ext_val

        return None, None

    def _compare_values(self, gt_val: Any, ext_val: Any) -> bool:
        """
        Compares ground truth value with extracted value.
        Supports exact match, string normalization, number matching, and token similarity.
        """
        norm_gt = normalize_value(gt_val)
        norm_ext = normalize_value(ext_val)

        if not norm_gt or not norm_ext:
            return False

        # Exact normalized match
        if norm_gt == norm_ext:
            return True

        # Sub-string inclusion for numbers or tokens (e.g. Aadhaar with/without spaces)
        if norm_gt in norm_ext or norm_ext in norm_gt:
            return True

        # Token similarity for address and longer text fields
        gt_str = str(gt_val).strip()
        ext_str = str(ext_val).strip()
        if len(gt_str) >= 8 or len(ext_str) >= 8:
            sim = token_similarity(gt_str, ext_str)
            if sim >= 0.75:
                return True

        return False

    def verify_extractions(
        self,
        document_extractions: List[Dict[str, Any]],
        user_detail: Optional[Dict[str, Any]] = None,
        person_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Verifies extracted details from multiple documents against user_detail ground truth dictionary or source/<person_id>.json.

        Scoring Rules:
        - If a ground truth attribute is matched: +1 point to match score.
        - If a ground truth attribute is missing in docs: 0 penalty (does not matter).
        - If an attribute value mismatches ground truth: -1 point penalty and flagged as MISMATCH.
        """
        if user_detail is not None:
            ground_truth_raw = user_detail
        elif person_id:
            ground_truth_raw = self.load_source_json(person_id)
        else:
            ground_truth_raw = {}

        ground_truth = self._flatten_data(ground_truth_raw)

        # Merge extracted data from all documents for this person
        all_extracted_flat: Dict[str, Any] = {}
        for doc in document_extractions:
            doc_data = doc.get("data", doc) if isinstance(doc, dict) else {}
            if isinstance(doc_data, dict):
                flat_doc = self._flatten_data(doc_data)
                for k, v in flat_doc.items():
                    if v is not None and str(v).strip():
                        all_extracted_flat[k] = v

        matched_fields: List[Dict[str, Any]] = []
        mismatched_fields: List[Dict[str, Any]] = []
        missing_fields: List[Dict[str, Any]] = []

        total_evaluable_gt_fields = 0
        matched_count = 0
        mismatch_count = 0

        for gt_key, gt_val in ground_truth.items():
            # Skip empty or null ground truth fields
            if gt_val is None or str(gt_val).strip() == "":
                continue

            total_evaluable_gt_fields += 1
            norm_gt_key = normalize_key(gt_key)

            ext_key, ext_val = self._find_matching_extracted_value(norm_gt_key, all_extracted_flat)

            if ext_key is None or ext_val is None or str(ext_val).strip() == "":
                missing_fields.append({
                    "field": gt_key,
                    "ground_truth_value": str(gt_val),
                    "status": "MISSING",
                    "note": "Field missing from extracted documents."
                })
            else:
                if self._compare_values(gt_val, ext_val):
                    matched_count += 1
                    matched_fields.append({
                        "field": gt_key,
                        "extracted_key": ext_key,
                        "ground_truth_value": str(gt_val),
                        "extracted_value": str(ext_val),
                        "status": "MATCH"
                    })
                else:
                    mismatch_count += 1
                    mismatched_fields.append({
                        "field": gt_key,
                        "extracted_key": ext_key,
                        "ground_truth_value": str(gt_val),
                        "extracted_value": str(ext_val),
                        "status": "MISMATCH",
                        "flagged": True,
                        "note": "Extracted value mismatches ground truth; score penalized."
                    })

        # Calculate Net Score: Matched (+1) - Mismatched (-1)
        net_score = max(0.0, float(matched_count - (2 * mismatch_count)))

        # Evaluated fields = fields present in extracted docs (matched + mismatched)
        # Missing fields do NOT affect or lower the confidence score
        evaluated_fields = matched_count + mismatch_count

        # Calculate Confidence Score percentage
        if evaluated_fields > 0:
            confidence_score = round((net_score / evaluated_fields) * 100.0, 2)
        else:
            confidence_score = 0.0

        display_name = (
            person_id
            or (user_detail.get("ApplicantName") if isinstance(user_detail, dict) else None)
            or (user_detail.get("applicant_name") if isinstance(user_detail, dict) else None)
            or "user"
        )
        return {
            "confidence_score": confidence_score,
            "total_ground_truth_fields": total_evaluable_gt_fields,
            "matched_count": matched_count,
            "mismatch_count": mismatch_count,
            "missing_count": len(missing_fields),
            "net_score": net_score,
            "matched_fields": matched_fields,
            "mismatched_fields": mismatched_fields,
            "missing_fields": missing_fields,
            "summary": (
                f"Evaluation for '{display_name}': {matched_count} matched, "
                f"{mismatch_count} mismatched , {len(missing_fields)} missing. "
                f"Confidence Score: {confidence_score}%"
            )
        }
