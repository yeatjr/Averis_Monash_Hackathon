"""FastAPI Web Application for SDOC Shipping Document Verification.

Provides an interactive operations dashboard:
- Live Verification Studio: Ingest custom documents (PDF, Word, Excel, Text) or test 1-click presets
- Side-by-side field discrepancy matrix with visual diff highlighting
- Human-in-the-loop escalation review and automated Carrier Discrepancy Notice drafting
- Official evaluation scoring against 520 benchmark emails and submission export
"""
import os
import sys
import glob
import json
import uuid
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Add root and server to sys.path
ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))
SERVER_DIR = ROOT / "sdoc-hackathon-docker" / "server"
sys.path.insert(0, str(SERVER_DIR))

import scoring
from solution.classifier import classify_email
from solution.extractors import extract_document, is_blank
from solution.comparator import compare_documents, normalize_field, COMPARE_FIELDS
from solution.pipeline import process_email

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Shipping Document Verification Dashboard", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = ROOT / "sdoc-hackathon-docker" / "data_v2"
INBOX_DIR = DATA_DIR / "inbox"
GROUND_TRUTH_PATH = DATA_DIR / "ground_truth.json"

# In-memory cached states and user review overrides
EMAIL_CACHE: Dict[str, Dict[str, Any]] = {}
DECISION_CACHE: Dict[str, Dict[str, Any]] = {}
HUMAN_OVERRIDES: Dict[str, Dict[str, Any]] = {}


def load_all():
    """Precompute all email decisions on startup."""
    global EMAIL_CACHE, DECISION_CACHE
    EMAIL_CACHE.clear()
    DECISION_CACHE.clear()

    files = sorted(glob.glob(str(INBOX_DIR / "email_*.json")))
    for f in files:
        with open(f, "r", encoding="utf-8") as fp:
            rec = json.load(fp)
        eid = rec["email_id"]
        EMAIL_CACHE[eid] = rec
        res = process_email(rec, base_dir=str(DATA_DIR))
        DECISION_CACHE[eid] = res


# Precompute on module load
load_all()

# =========================================================================
# LIVE VERIFICATION STUDIO PRESETS
# =========================================================================
PRESETS = [
    {
        "id": "clean_match",
        "name": "Clean Match — Maersk Ocean Line",
        "tag": "PASSED (OK)",
        "badge_color": "green",
        "description": "Perfect 7-field alignment between Shipping Instruction and carrier draft B/L. Ready for customs clearance.",
        "email": {
            "from": "docs-team@asiapacific-logistics.com",
            "subject": "Verify BL vs SI - Booking MSK-9823412 - 2x40HC Chemicals",
            "body": "Dear Maersk Documentation Team,\n\nPlease verify the draft BL attached matches our confirmed Shipping Instruction for booking MSK-9823412.\nCargo is scheduled to load at Singapore this Friday.\n\nBest regards,\nDocumentation Dept."
        },
        "si_fields": {
            "shipper": "Asia Pacific Petrochemicals Pte Ltd\n12 Marina View #21-01 Asia Square Tower 2, Singapore 018961",
            "consignee": "Rotterdam Logistics BV\nMaasvlakte 2, Haven 9200, 3011 AD Rotterdam, Netherlands",
            "notify_party": "Same as Consignee",
            "port_of_loading": "Singapore (SGSIN)",
            "port_of_discharge": "Rotterdam (NLRTM)",
            "container_count": "2 x 40'HC",
            "gross_weight_kg": "48,250 KGS"
        },
        "bl_fields": {
            "shipper": "Asia Pacific Petrochemicals Pte Ltd\n12 Marina View #21-01 Asia Square Tower 2, Singapore 018961",
            "consignee": "Rotterdam Logistics BV\nMaasvlakte 2, Haven 9200, 3011 AD Rotterdam, Netherlands",
            "notify_party": "Same as Consignee",
            "port_of_loading": "Singapore (SGSIN)",
            "port_of_discharge": "Rotterdam (NLRTM)",
            "container_count": "2 x 40'HC",
            "gross_weight_kg": "48,250 KGS"
        }
    },
    {
        "id": "weight_container_mismatch",
        "name": "Weight & Container Mismatch",
        "tag": "DISCREPANCY (MISMATCH)",
        "badge_color": "red",
        "description": "Critical discrepancies in gross weight (-6,058 kg) and container count (6 vs 5) between SI declaration and carrier draft.",
        "email": {
            "from": "shipping@global-electronics.sz",
            "subject": "Urgent - Check Draft BL against SI - Booking COSCO-77412",
            "body": "Hi Documentation Desk,\n\nAttached are our SI and carrier draft B/L for Booking COSCO-77412. Please confirm if draft is approved for issuance.\n\nRegards,\nShenzhen Logistics"
        },
        "si_fields": {
            "shipper": "Shenzhen Global Electronics Ltd\nHigh-Tech Industrial Park, Nanshan, Shenzhen, China",
            "consignee": "Pacific Rim Trading LLC\n1420 Harbor Blvd, Long Beach, CA 90802, USA",
            "notify_party": "Trans-Pacific Freight Services Inc\nLos Angeles, CA",
            "port_of_loading": "Shenzhen (CNSZX)",
            "port_of_discharge": "Long Beach (USLGB)",
            "container_count": "6 x 40'GP",
            "gross_weight_kg": "131,058 KG"
        },
        "bl_fields": {
            "shipper": "Shenzhen Global Electronics Ltd\nHigh-Tech Industrial Park, Nanshan, Shenzhen, China",
            "consignee": "Pacific Rim Trading LLC\n1420 Harbor Blvd, Long Beach, CA 90802, USA",
            "notify_party": "Trans-Pacific Freight Services Inc\nLos Angeles, CA",
            "port_of_loading": "Shenzhen (CNSZX)",
            "port_of_discharge": "Long Beach (USLGB)",
            "container_count": "5 x 40'GP",
            "gross_weight_kg": "125,000 KG"
        }
    },
    {
        "id": "port_mismatch",
        "name": "Port Alias / Routing Discrepancy",
        "tag": "PORT MISMATCH",
        "badge_color": "red",
        "description": "Discrepancy in Port of Loading: Shipper booked Shanghai (CNSHA), but draft BL manifests Ningbo (CNNGB).",
        "email": {
            "from": "export@goldensilk-textiles.cn",
            "subject": "Draft BL Checking - Booking HLC-99023 - Textiles",
            "body": "Hello Hapag-Lloyd Docs,\n\nPlease verify attached draft BL against our final shipping instructions before vessel departure.\n\nThanks,\nGolden Silk Textiles Co."
        },
        "si_fields": {
            "shipper": "Zhejiang Golden Silk Textiles Co., Ltd\nNo. 88 Silk Road, Shaoxing, Zhejiang, China",
            "consignee": "Hamburg Fashion Distribution GmbH\nSpeicherstadt Block D, 20457 Hamburg, Germany",
            "notify_party": "Same as Consignee",
            "port_of_loading": "Shanghai (CNSHA)",
            "port_of_discharge": "Hamburg (DEHAM)",
            "container_count": "3 x 40'HC",
            "gross_weight_kg": "34,500 KG"
        },
        "bl_fields": {
            "shipper": "Zhejiang Golden Silk Textiles Co., Ltd\nNo. 88 Silk Road, Shaoxing, Zhejiang, China",
            "consignee": "Hamburg Fashion Distribution GmbH\nSpeicherstadt Block D, 20457 Hamburg, Germany",
            "notify_party": "Same as Consignee",
            "port_of_loading": "Ningbo (CNNGB)",
            "port_of_discharge": "Hamburg (DEHAM)",
            "container_count": "3 x 40'HC",
            "gross_weight_kg": "34,500 KG"
        }
    },
    {
        "id": "missing_consignee",
        "name": "Missing Mandatory Field (Consignee TBA)",
        "tag": "RELIABILITY (NEEDS REVIEW)",
        "badge_color": "amber",
        "description": "Reliability guardrail triggered: Mandatory consignee is unspecified / marked 'TBA'. Human escalation required.",
        "email": {
            "from": "logistics@indowood.co.id",
            "subject": "Review Draft BL - Booking CMA-10294",
            "body": "Dear CMA CGM team,\n\nPlease find draft BL attached. Note buyer final details are pending confirmation.\n\nRegards,\nIndo Wood Resources"
        },
        "si_fields": {
            "shipper": "PT Indo Wood Resources\nJl. Industri Raya No. 45, Jakarta 14350, Indonesia",
            "consignee": "TBA",
            "notify_party": "Indo Wood Logistics Singapore",
            "port_of_loading": "Jakarta (IDJKT)",
            "port_of_discharge": "Sydney (AUSAU)",
            "container_count": "1 x 20'GP",
            "gross_weight_kg": "18,200 KG"
        },
        "bl_fields": {
            "shipper": "PT Indo Wood Resources\nJl. Industri Raya No. 45, Jakarta 14350, Indonesia",
            "consignee": "Sydney Timber Importers Pty Ltd\n78 Botany Rd, Alexandria NSW 2015, Australia",
            "notify_party": "Indo Wood Logistics Singapore",
            "port_of_loading": "Jakarta (IDJKT)",
            "port_of_discharge": "Sydney (AUSAU)",
            "container_count": "1 x 20'GP",
            "gross_weight_kg": "18,200 KG"
        }
    },
    {
        "id": "wrong_doc_type",
        "name": "Wrong Document Attached (Packing List)",
        "tag": "GUARDRAIL (WRONG DOC)",
        "badge_color": "amber",
        "description": "Reliability guardrail triggered: Customer mistakenly attached a Packing List / Invoice instead of a Bill of Lading.",
        "email": {
            "from": "ops@forwarding-partners.com",
            "subject": "Attached documents for B/L checking - Booking ONE-88219",
            "body": "Good day,\n\nPlease find attached docs for your immediate review and confirmation.\n\nWarm regards,\nForwarding Partners"
        },
        "si_fields": {
            "shipper": "Vietnam Agro Commodities JSC\nDistrict 7, Ho Chi Minh City, Vietnam",
            "consignee": "Tokyo Food Imports KK\nChiyoda-ku, Tokyo 100-0005, Japan",
            "notify_party": "Same as Consignee",
            "port_of_loading": "Ho Chi Minh (VNSGN)",
            "port_of_discharge": "Tokyo (TYO)",
            "container_count": "4 x 40'RF",
            "gross_weight_kg": "88,000 KG"
        },
        "bl_fields": {},
        "special_trigger": "wrong_doc_type"
    },
    {
        "id": "unreadable_corrupt",
        "name": "Corrupted / Unreadable Document",
        "tag": "GUARDRAIL (UNREADABLE)",
        "badge_color": "amber",
        "description": "Reliability guardrail triggered: Document contains corrupt byte streams or unextractable text. Flagged for operator review.",
        "email": {
            "from": "traffic@intermodal-sea.com",
            "subject": "Draft BL checking - Booking MSC-33012",
            "body": "Dear Docs Team,\n\nDraft BL attached for vessel MSC OSCAR. Please confirm asap.\n\nRegards,\nIntermodal Sea Ops"
        },
        "si_fields": {
            "shipper": "Apex Engineering Supplies Ltd\nBirmingham B1 1AA, United Kingdom",
            "consignee": "Dubai Industrial Supplies LLC\nJebel Ali Free Zone, Dubai, UAE",
            "notify_party": "Same as Consignee",
            "port_of_loading": "Southampton (GBSOU)",
            "port_of_discharge": "Jebel Ali (AEJEA)",
            "container_count": "2 x 40'OT",
            "gross_weight_kg": "29,400 KG"
        },
        "bl_fields": {},
        "special_trigger": "unreadable"
    }
]


def build_detailed_comparison(si_fields: Dict[str, Any], bl_fields: Dict[str, Any], special_trigger: Optional[str] = None) -> Dict[str, Any]:
    """Perform side-by-side comparison with full per-field breakdown for the UI."""
    if special_trigger == "wrong_doc_type":
        return {
            "status": "NEEDS_REVIEW",
            "review_reason": "wrong_doc_type",
            "has_defect": False,
            "defect_fields": [],
            "comparison": {},
            "notes": "Attached document identified as Commercial Invoice / Packing List instead of Bill of Lading."
        }
    if special_trigger == "unreadable":
        return {
            "status": "NEEDS_REVIEW",
            "review_reason": "unreadable",
            "has_defect": False,
            "defect_fields": [],
            "comparison": {},
            "notes": "Attachment unreadable or corrupted byte stream detected."
        }

    # Standard comparison
    base_res = compare_documents(si_fields, bl_fields)

    # Enrich comparison dictionary so all 7 fields are present with their status
    details = {}
    for f in COMPARE_FIELDS:
        si_raw = si_fields.get(f)
        bl_raw = bl_fields.get(f)
        si_blank = is_blank(si_raw)
        bl_blank = is_blank(bl_raw)

        si_norm = normalize_field(f, si_raw) if not si_blank else None
        bl_norm = normalize_field(f, bl_raw) if not bl_blank else None

        if si_blank:
            status = "MISSING_SI"
            match = False
        elif bl_blank:
            status = "MISSING_BL"
            match = False
        else:
            match = (si_norm == bl_norm)
            status = "MATCH" if match else "MISMATCH"

        details[f] = {
            "si_raw": si_raw,
            "bl_raw": bl_raw,
            "si_normalized": si_norm,
            "bl_normalized": bl_norm,
            "match": match,
            "status": status
        }

    return {
        "status": base_res["status"],
        "review_reason": base_res["review_reason"],
        "has_defect": base_res["has_defect"],
        "defect_fields": base_res["defect_fields"],
        "comparison": details
    }


# =========================================================================
# STUDIO API ENDPOINTS
# =========================================================================
@app.get("/api/presets")
def get_presets():
    """Return interactive presets for 1-click user workflow testing."""
    return PRESETS


@app.post("/api/verify-custom")
def verify_custom(payload: Dict[str, Any] = Body(...)):
    """Run verification against custom JSON payload (preset, manual edit, or simulated email)."""
    subject = payload.get("subject", "Shipping Document Verification Request")
    body = payload.get("body", "Please verify attached SI and Draft BL.")
    from_email = payload.get("from", "operator@logistics-desk.com")
    attachments = payload.get("attachments", ["si_document.txt", "bl_document.txt"])

    email_record = {
        "email_id": f"LIVE-{uuid.uuid4().hex[:8].upper()}",
        "from": from_email,
        "subject": subject,
        "body": body,
        "attachments": attachments
    }

    category = classify_email(email_record)

    si_fields = payload.get("si_fields", {})
    bl_fields = payload.get("bl_fields", {})
    special_trigger = payload.get("special_trigger")

    comp_res = build_detailed_comparison(si_fields, bl_fields, special_trigger=special_trigger)

    return {
        "verification_id": email_record["email_id"],
        "category": category,
        "status": comp_res["status"],
        "review_reason": comp_res["review_reason"],
        "has_defect": comp_res["has_defect"],
        "defect_fields": comp_res["defect_fields"],
        "comparison": comp_res["comparison"],
        "notes": comp_res.get("notes"),
        "si_fields": si_fields,
        "bl_fields": bl_fields,
        "email": email_record
    }


@app.post("/api/verify-files")
async def verify_files(
    si: Optional[UploadFile] = File(None),
    bl: Optional[UploadFile] = File(None),
    si_file: Optional[UploadFile] = File(None),
    bl_file: Optional[UploadFile] = File(None),
    subject: str = Form("Shipping Instruction & Draft BL Verification"),
    body: str = Form("Please check draft BL matches the SI."),
    from_email: str = Form("docs@shipper.com")
):
    """Ingest uploaded SI and BL files (.pdf, .docx, .xlsx, .txt) and run autonomous extraction & comparison."""
    temp_dir = tempfile.mkdtemp(prefix="sdoc_upload_")
    try:
        si_text, bl_text = "", ""
        doc_si, doc_bl = {"status": "UNREADABLE", "fields": {}}, {"status": "UNREADABLE", "fields": {}}

        actual_si = si or si_file
        actual_bl = bl or bl_file

        # Save and extract SI
        if actual_si and actual_si.filename:
            si_path = os.path.join(temp_dir, f"si_{actual_si.filename}")
            with open(si_path, "wb") as f:
                content = await actual_si.read()
                f.write(content)
            doc_si = extract_document(si_path)
            si_text = doc_si.get("text", "")

        # Save and extract BL
        if actual_bl and actual_bl.filename:
            bl_path = os.path.join(temp_dir, f"bl_{actual_bl.filename}")
            with open(bl_path, "wb") as f:
                content = await actual_bl.read()
                f.write(content)
            doc_bl = extract_document(bl_path)
            bl_text = doc_bl.get("text", "")

        # Email classification
        email_record = {
            "email_id": f"UPLOAD-{uuid.uuid4().hex[:8].upper()}",
            "from": from_email,
            "subject": subject,
            "body": body,
            "attachments": [f for f in [actual_si.filename if actual_si else None, actual_bl.filename if actual_bl else None] if f]
        }
        category = classify_email(email_record)

        # Check guardrails
        if doc_si.get("status") == "UNREADABLE" or doc_bl.get("status") == "UNREADABLE":
            comp_res = {
                "status": "NEEDS_REVIEW",
                "review_reason": "unreadable",
                "has_defect": False,
                "defect_fields": [],
                "comparison": {}
            }
        elif doc_si.get("status") == "WRONG_DOC_TYPE" or doc_bl.get("status") == "WRONG_DOC_TYPE":
            comp_res = {
                "status": "NEEDS_REVIEW",
                "review_reason": "wrong_doc_type",
                "has_defect": False,
                "defect_fields": [],
                "comparison": {}
            }
        else:
            comp_res = build_detailed_comparison(doc_si.get("fields", {}), doc_bl.get("fields", {}))

        return {
            "verification_id": email_record["email_id"],
            "category": category,
            "status": comp_res["status"],
            "review_reason": comp_res["review_reason"],
            "has_defect": comp_res["has_defect"],
            "defect_fields": comp_res["defect_fields"],
            "comparison": comp_res["comparison"],
            "si_fields": doc_si.get("fields", {}),
            "bl_fields": doc_bl.get("fields", {}),
            "si_text": si_text[:4000],
            "bl_text": bl_text[:4000],
            "email": email_record
        }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# =========================================================================
# ORGANIZER BENCHMARK DATASET ENDPOINTS (520 EMAILS)
# =========================================================================
@app.get("/api/health")
def api_health():
    """Health check endpoint for dashboard connectivity."""
    return {"status": "ok", "total_emails": len(EMAIL_CACHE)}


@app.get("/api/emails")
def get_emails(category: Optional[str] = None, status: Optional[str] = None, q: Optional[str] = None):
    """List all 520 benchmark emails with precomputed status, search, and category filters."""
    results = []
    for eid, email in EMAIL_CACHE.items():
        dec = HUMAN_OVERRIDES.get(eid) or DECISION_CACHE.get(eid, {})

        if category and category.upper() != "ALL" and dec.get("category") != category.upper():
            continue
        if status and status.upper() != "ALL" and dec.get("status") != status.upper():
            continue
        if q:
            ql = q.lower()
            if ql not in eid.lower() and ql not in email.get("subject", "").lower() and ql not in email.get("from", "").lower():
                continue

        results.append({
            "email_id": eid,
            "from": email.get("from", ""),
            "subject": email.get("subject", ""),
            "attachments_count": len(email.get("attachments", [])),
            "category": dec.get("category"),
            "status": dec.get("status"),
            "review_reason": dec.get("review_reason"),
            "has_defect": dec.get("has_defect"),
            "defect_fields": dec.get("defect_fields", []),
            "is_human_reviewed": eid in HUMAN_OVERRIDES
        })
    return results


@app.get("/api/email/{email_id}")
def get_email_detail(email_id: str):
    """Get full details for a single email record including attachments and comparison."""
    if email_id not in EMAIL_CACHE:
        raise HTTPException(status_code=404, detail="Email not found")

    email = EMAIL_CACHE[email_id]
    dec = HUMAN_OVERRIDES.get(email_id) or DECISION_CACHE.get(email_id, {})

    attachments_info = []
    for att in email.get("attachments", []):
        att_path = DATA_DIR / att
        info = {
            "path": att,
            "filename": os.path.basename(att),
            "size": os.path.getsize(att_path) if os.path.exists(att_path) else 0,
            "exists": os.path.exists(att_path)
        }
        if os.path.exists(att_path):
            doc_res = extract_document(str(att_path))
            info["doc_type"] = doc_res.get("status")
            info["fields"] = doc_res.get("fields", {})
            info["text_preview"] = doc_res.get("text", "")[:3000]
        attachments_info.append(info)

    # Build fields dict if available
    extracted_fields = {}
    if dec.get("comparison_details"):
        for f, val_info in dec["comparison_details"].items():
            extracted_fields[f] = {
                "si": val_info.get("si_raw", ""),
                "bl": val_info.get("bl_raw", "")
            }

    return {
        "email_id": email_id,
        "from": email.get("from", ""),
        "subject": email.get("subject", ""),
        "body": email.get("body", ""),
        "date": email.get("date", ""),
        "category": dec.get("category"),
        "status": dec.get("status"),
        "email": email,
        "decision": dec,
        "fields": extracted_fields,
        "attachments": attachments_info,
        "is_human_reviewed": email_id in HUMAN_OVERRIDES
    }


@app.post("/api/human-review/{email_id}")
def submit_human_review(email_id: str, payload: Dict[str, Any] = Body(...)):
    """Allow human operators to update/override verification results or fill in missing values."""
    if email_id not in EMAIL_CACHE:
        raise HTTPException(status_code=404, detail="Email not found")

    overrides = payload.get("overrides")
    if overrides and isinstance(overrides, dict):
        si_fields = {f: (v.get("si", "") if isinstance(v, dict) else v) for f, v in overrides.items()}
        bl_fields = {f: (v.get("bl", "") if isinstance(v, dict) else v) for f, v in overrides.items()}
    else:
        si_fields = payload.get("si_fields")
        bl_fields = payload.get("bl_fields")

    if si_fields is not None and bl_fields is not None:
        comp = compare_documents(si_fields, bl_fields)
        HUMAN_OVERRIDES[email_id] = {
            "category": "BL_COMPARISON",
            "status": comp["status"],
            "review_reason": comp["review_reason"],
            "defect_fields": comp["defect_fields"],
            "has_defect": comp["has_defect"],
            "comparison_details": comp.get("comparison", {}),
            "human_notes": payload.get("notes", "Operator reviewed and updated values")
        }
    else:
        HUMAN_OVERRIDES[email_id] = {
            "category": payload.get("category", "BL_COMPARISON"),
            "status": payload.get("status", "OK"),
            "review_reason": payload.get("review_reason"),
            "defect_fields": payload.get("defect_fields", []),
            "has_defect": bool(payload.get("defect_fields")),
            "human_notes": payload.get("notes", "Operator manually updated status")
        }

    return {"status": "success", "decision": HUMAN_OVERRIDES[email_id]}


@app.get("/api/metrics")
def get_metrics():
    """Compute live metrics across all 520 emails against ground truth."""
    if not os.path.exists(GROUND_TRUTH_PATH):
        raise HTTPException(status_code=404, detail="Ground truth file not found")

    with open(GROUND_TRUTH_PATH, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    submission = {}
    for eid in EMAIL_CACHE:
        dec = HUMAN_OVERRIDES.get(eid) or DECISION_CACHE.get(eid, {})
        submission[eid] = {
            "category": dec["category"],
            "status": dec["status"],
            "review_reason": dec["review_reason"],
            "defect_fields": dec["defect_fields"],
            "has_defect": dec["has_defect"]
        }

    scores = scoring.score_all(ground_truth, submission)
    return scores


@app.get("/api/export/submission")
def export_submission():
    """Export the current submission dictionary as JSON."""
    submission = {}
    for eid in EMAIL_CACHE:
        dec = HUMAN_OVERRIDES.get(eid) or DECISION_CACHE.get(eid, {})
        submission[eid] = {
            "category": dec["category"],
            "status": dec["status"],
            "review_reason": dec["review_reason"],
            "defect_fields": dec["defect_fields"],
            "has_defect": dec["has_defect"]
        }
    return JSONResponse(content=submission, headers={
        "Content-Disposition": "attachment; filename=submission.json"
    })


# Static assets
STATIC_DIR = ROOT / "web" / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        return HTMLResponse("<h1>Dashboard UI Loading...</h1>")
    return HTMLResponse(index_file.read_text(encoding="utf-8"))
