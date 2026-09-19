"""Shipping document comparison engine for SDOC hackathon.

Compares normalized shipment fields between Shipping Instruction (reference)
and draft Bill of Lading. Detects field discrepancies and flags missing required
values for human-in-the-loop escalation.
"""
from typing import Dict, Any, List, Tuple
from solution.extractors import (
    clean_party,
    clean_port,
    clean_container_count,
    clean_weight,
    is_blank
)

COMPARE_FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg"
]


def normalize_field(field_name: str, val: Any) -> Any:
    """Normalize a raw field value according to its field type."""
    if field_name in ("shipper", "consignee", "notify_party"):
        return clean_party(val)
    if field_name in ("port_of_loading", "port_of_discharge"):
        return clean_port(val)
    if field_name == "container_count":
        return clean_container_count(val)
    if field_name == "gross_weight_kg":
        return clean_weight(val)
    return str(val).strip() if val is not None else ""


def compare_documents(si_fields: Dict[str, Any], bl_fields: Dict[str, Any]) -> Dict[str, Any]:
    """Compare extracted SI and BL fields.

    Returns comparison dict with:
    - status: 'OK' | 'MISMATCH' | 'NEEDS_REVIEW'
    - review_reason: None | 'missing_value'
    - has_defect: bool
    - defect_fields: List[str]
    - comparison: Dict[str, Dict[str, Any]] with side-by-side details
    """
    # 1. Check for missing / blank values in SI
    for f in COMPARE_FIELDS:
        if f not in si_fields or is_blank(si_fields.get(f)):
            return {
                "status": "NEEDS_REVIEW",
                "review_reason": "missing_value",
                "has_defect": False,
                "defect_fields": [],
                "comparison": {}
            }

    # 2. Field-by-field side-by-side comparison
    mismatches: List[str] = []
    comparison_details = {}

    for f in COMPARE_FIELDS:
        si_norm = normalize_field(f, si_fields.get(f))
        bl_norm = normalize_field(f, bl_fields.get(f))

        match = (si_norm == bl_norm)
        comparison_details[f] = {
            "si_raw": si_fields.get(f),
            "bl_raw": bl_fields.get(f),
            "si_normalized": si_norm,
            "bl_normalized": bl_norm,
            "match": match
        }

        if not match:
            mismatches.append(f)

    if mismatches:
        return {
            "status": "MISMATCH",
            "review_reason": None,
            "has_defect": True,
            "defect_fields": sorted(mismatches),
            "comparison": comparison_details
        }

    return {
        "status": "OK",
        "review_reason": None,
        "has_defect": False,
        "defect_fields": [],
        "comparison": comparison_details
    }
