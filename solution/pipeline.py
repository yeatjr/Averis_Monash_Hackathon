"""End-to-End Verification Pipeline for SDOC Hackathon.

Orchestrates email ingestion, classification, document extraction,
reliability guardrails, and discrepancy reporting.
"""
import os
import re
from typing import Dict, Any, Optional
from solution.classifier import classify_email
from solution.extractors import extract_document
from solution.comparator import compare_documents


def process_email(email_record: Dict[str, Any], base_dir: str = ".") -> Dict[str, Any]:
    """Process a single email record and produce the verification decision."""
    category = classify_email(email_record)

    # If not a BL comparison request, no document checking needed
    if category != "BL_COMPARISON":
        return {
            "category": category,
            "status": "OK",
            "review_reason": None,
            "defect_fields": [],
            "has_defect": False
        }

    attachments = email_record.get("attachments", [])
    body = email_record.get("body", "").lower()

    # Reliability check: Missing attachments
    if len(attachments) == 0:
        # Check if intended to compare documents but attachments missing/dropped
        if ("compare the si and draft bl" in body or
            "draft bl is still missing" in body or
            "dropped" in body):
            return {
                "category": "BL_COMPARISON",
                "status": "NEEDS_REVIEW",
                "review_reason": "missing_attachment",
                "defect_fields": [],
                "has_defect": False
            }
        # Routine operational request to send draft BL (no attachments expected yet)
        return {
            "category": "BL_COMPARISON",
            "status": "OK",
            "review_reason": None,
            "defect_fields": [],
            "has_defect": False
        }

    if len(attachments) == 1:
        # Comparison requested but only 1 attachment provided
        return {
            "category": "BL_COMPARISON",
            "status": "NEEDS_REVIEW",
            "review_reason": "missing_attachment",
            "defect_fields": [],
            "has_defect": False
        }

    # Resolve SI and BL attachment paths
    att1, att2 = attachments[0], attachments[1]
    p1 = os.path.join(base_dir, att1)
    p2 = os.path.join(base_dir, att2)

    if "_si" in att1.lower() or "_bl" in att2.lower():
        si_path, bl_path = p1, p2
    elif "_bl" in att1.lower() or "_si" in att2.lower():
        si_path, bl_path = p2, p1
    else:
        si_path, bl_path = p1, p2

    # Extract documents
    doc_si = extract_document(si_path)
    doc_bl = extract_document(bl_path)

    # Reliability check: Unreadable files
    if doc_si["status"] == "UNREADABLE" or doc_bl["status"] == "UNREADABLE":
        return {
            "category": "BL_COMPARISON",
            "status": "NEEDS_REVIEW",
            "review_reason": "unreadable",
            "defect_fields": [],
            "has_defect": False,
            "details": {"si_status": doc_si["status"], "bl_status": doc_bl["status"]}
        }

    # Reliability check: Wrong document type attached
    if doc_si["status"] == "WRONG_DOC_TYPE" or doc_bl["status"] == "WRONG_DOC_TYPE":
        return {
            "category": "BL_COMPARISON",
            "status": "NEEDS_REVIEW",
            "review_reason": "wrong_doc_type",
            "defect_fields": [],
            "has_defect": False,
            "details": {"si_reason": doc_si.get("reason"), "bl_reason": doc_bl.get("reason")}
        }

    # Compare extracted fields (handles missing_value detection inside)
    comparison = compare_documents(doc_si["fields"], doc_bl["fields"])

    return {
        "category": "BL_COMPARISON",
        "status": comparison["status"],
        "review_reason": comparison["review_reason"],
        "defect_fields": comparison["defect_fields"],
        "has_defect": comparison["has_defect"],
        "comparison_details": comparison.get("comparison", {})
    }
