"""Email classification module for SDOC hackathon.

Classifies incoming shipping operations emails into one of 5 categories:
- BL_COMPARISON
- SI_REQUEST
- INVOICE_QUERY
- GENERAL
- SPAM
"""
import re

CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]

SPAM_KEYWORDS = [
    r"gift card", r"parcel is on hold", r"storage is full", r"90% off",
    r"bank details", r"undelivered messages", r"one weird trick",
    r"avoid suspension", r"hot singles", r"bitcoin", r"congratulations",
    r"crypto", r"iphone", r"prize-claims", r"parcel-track", r"webmail-verify",
    r"logistics-deals\.biz", r"crypto-invest", r"secure-mailbox"
]

INVOICE_KEYWORDS = [
    r"missing gr\b", r"cancel invoice", r"local charges", r"d\s*&\s*d charges",
    r"detention charges", r"total freight", r"reverse the pgi", r"query on invoice",
    r"billing.*missing gr", r"thc / local charge"
]

GENERAL_KEYWORDS = [
    r"update summary", r"berthing report", r"submit si & aed",
    r"_rpa_.*billing process", r"outstanding bl\b", r"pending bl release",
    r"new year", r"time off request", r"miss connection", r"delivery planning",
    r"rpa\.bot@", r"hr@aprilasia", r"noreply@"
]

SI_REQUEST_SUBJECT_PATTERNS = [
    r"^re_?\s*si\s*-",
    r"^si\s*-",
    r"\bcust si\b",
    r"\brequest si\b",
    r"\bsi needed\b",
    r"\blatest si\b"
]

BL_COMPARISON_PATTERNS = [
    r"to confirm docs",
    r"request bl draft",
    r"draft bl.*amend bl",
    r"verify the bl matches the si",
    r"attached are the si and draft bl",
    r"check the draft bl against the si",
    r"send the draft bl.*for checking",
    r"compare the si and draft bl",
    r"si and the .* for .* kindly confirm the bl is in order",
    r"attached si and draft bl.*for checking"
]

# Coded pattern: e.g. "AIE - POD - CARRIER(BL#) - OC - INV - CUSTOMER - TERM"
CODED_BL_PATTERN = re.compile(
    r"(AIE|AFPTME|AFRT|AFEMY)\s*-\s*[^-\n]+\s*-\s*[A-Z0-9]+(?:\([^\)]+\))?\s*-\s*5[A-Z0-9]+-[0-9]+\s*-\s*5[0-9]+\s*-\s*[^-\n]+",
    re.IGNORECASE
)


def classify_email(email_record: dict) -> str:
    """Classify an email record into one of 5 categories."""
    subject = email_record.get("subject", "")
    body = email_record.get("body", "")
    sender = email_record.get("from", "")
    clean_sub = subject.strip().lower()
    combined_text = f"{subject}\n{sender}\n{body}".lower()

    # 1. SPAM check
    for kw in SPAM_KEYWORDS:
        if re.search(kw, combined_text):
            return "SPAM"

    # 2. INVOICE_QUERY check
    for kw in INVOICE_KEYWORDS:
        if re.search(kw, combined_text):
            return "INVOICE_QUERY"

    # 3. GENERAL check
    for kw in GENERAL_KEYWORDS:
        if re.search(kw, combined_text):
            return "GENERAL"

    # 4. SI_REQUEST check
    # Check specific SI request subject patterns
    for pat in SI_REQUEST_SUBJECT_PATTERNS:
        if re.search(pat, clean_sub):
            return "SI_REQUEST"

    # Check body for SI request indicators (body contains "Please find Shipping instruction for" and "Documents Required")
    if "please find shipping instruction for" in body.lower() and "documents required" in body.lower():
        return "SI_REQUEST"

    # 5. BL_COMPARISON check
    for pat in BL_COMPARISON_PATTERNS:
        if re.search(pat, combined_text):
            return "BL_COMPARISON"

    if CODED_BL_PATTERN.search(subject):
        return "BL_COMPARISON"

    # Secondary heuristic for BL comparison
    if ("bl" in clean_sub or "draft" in clean_sub) and ("check" in body.lower() or "confirm" in body.lower()):
        return "BL_COMPARISON"

    # Fallback to GENERAL if unclassified
    return "GENERAL"
