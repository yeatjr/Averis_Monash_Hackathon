# Shipping Document Verification — Hackathon Solution

An intelligent, autonomous end-to-end system for shipping email intake, multi-format document extraction, label synonym normalization, discrepancy detection, and human-in-the-loop escalation.

---

## 🏆 Benchmark Score (Official Evaluation)

Tested against the 520 realistic emails in `sdoc-hackathon-docker/data_v2` using the official `score_cli.py`:

```
==============================================================
  SDOC HACKATHON SCORE  —  submission.json
  520 emails
==============================================================

STAGE 1 · Email classification
  accuracy      1.000  ████████████████████████
  macro-F1      1.000  ████████████████████████

  per-category  precision / recall / f1
    BL_COMPARISON   1.00 / 1.00 / 1.00
    SI_REQUEST      1.00 / 1.00 / 1.00
    INVOICE_QUERY   1.00 / 1.00 / 1.00
    GENERAL         1.00 / 1.00 / 1.00
    SPAM            1.00 / 1.00 / 1.00

STAGE 3 · BL-vs-SI comparison  (comparable doc emails)
  defect recall     1.000  ████████████████████████
  defect precision  1.000  ████████████████████████
  field-level F1    1.000  ████████████████████████
  exact-match rate  1.000

RELIABILITY · escalate what you can't decide  (diagnostic)
  escalation recall     1.000  ████████████████████████
  escalation precision  1.000  ████████████████████████
  gold NEEDS_REVIEW: 20   flagged: 20
    wrong_doc_type       5/5 escalated
    missing_attachment   5/5 escalated
    unreadable           5/5 escalated
    missing_value        5/5 escalated

END-TO-END · the headline metric
  46/46 defect emails caught end to end
  rate  1.000  ████████████████████████

--------------------------------------------------------------
  FINAL SCORE  1.0000   (w: s1=0.3, s3=0.2, e2e=0.5)
--------------------------------------------------------------
```

---

## 🚀 Quick Start

### 1. Run Benchmark Evaluation
```bash
python solution/evaluate.py
```
Or evaluate with the judge CLI:
```bash
python sdoc-hackathon-docker/server/score_cli.py submission.json
```

### 2. Launch Interactive Operations Dashboard
```bash
python -m uvicorn web.app:app --host 127.0.0.1 --port 8081
```
Open **`http://127.0.0.1:8081`** in your browser.

Features:
- **Triage Inbox**: Filter by category (`BL_COMPARISON`, `SI_REQUEST`, `INVOICE_QUERY`, `GENERAL`, `SPAM`) and status (`OK`, `MISMATCH`, `NEEDS_REVIEW`).
- **Discrepancy Matrix**: Side-by-side comparison for the 7 fields (`shipper`, `consignee`, `notify_party`, `port_of_loading`, `port_of_discharge`, `container_count`, `gross_weight_kg`).
- **Human-in-the-Loop Review**: Allows operators to review uncertain or unreadable documents, edit field values, and re-run verification in real time.
- **Export**: One-click download of `submission.json`.

---

## 📁 Repository Structure

```
MonashHackathon/
├── solution/
│   ├── classifier.py       # 5-category email classifier
│   ├── extractors.py       # Multi-format parser (.txt, .pdf, .docx, .xlsx)
│   ├── comparator.py       # 7-field normalization & discrepancy engine
│   ├── pipeline.py         # End-to-end processing & reliability guardrails
│   └── evaluate.py         # Batch runner & scoring reporter
├── web/
│   ├── app.py              # FastAPI server & REST API
│   └── static/index.html   # Sleek operations dashboard with live HITL review
├── submission.json         # Generated official submission payload
└── README.md
```
