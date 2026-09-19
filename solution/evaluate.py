"""Evaluation script for SDOC hackathon.

Runs the pipeline across the dataset and grades against ground_truth.json
using the official scoring module.
"""
import os
import sys
import glob
import json
from pathlib import Path

# Add server directory to path to import scoring
HERE = Path(__file__).parent.resolve()
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
SERVER_DIR = ROOT / "sdoc-hackathon-docker" / "server"
sys.path.insert(0, str(SERVER_DIR))

import scoring
from solution.pipeline import process_email


def evaluate(data_dir: str = None, ground_truth_file: str = None):
    if data_dir is None:
        data_dir = str(ROOT / "sdoc-hackathon-docker" / "data_v2")
    if ground_truth_file is None:
        ground_truth_file = os.path.join(data_dir, "ground_truth.json")

    inbox_dir = os.path.join(data_dir, "inbox")
    email_files = sorted(glob.glob(os.path.join(inbox_dir, "email_*.json")))
    ground_truth = json.loads(Path(ground_truth_file).read_text(encoding="utf-8"))

    print(f"Loaded {len(email_files)} emails from {inbox_dir}")
    print(f"Loaded {len(ground_truth)} ground truth records")

    submission = {}
    mismatches_recorded = []

    for fpath in email_files:
        with open(fpath, "r", encoding="utf-8") as f:
            rec = json.load(f)
        eid = rec["email_id"]
        res = process_email(rec, base_dir=data_dir)

        submission[eid] = {
            "category": res["category"],
            "status": res["status"],
            "review_reason": res["review_reason"],
            "defect_fields": res["defect_fields"],
            "has_defect": res["has_defect"]
        }

        # Compare with ground truth for diagnostics
        gt = ground_truth.get(eid, {})
        diffs = []
        if res["category"] != gt.get("category"):
            diffs.append(f"category: pred={res['category']} actual={gt.get('category')}")
        if res["status"] != gt.get("status"):
            diffs.append(f"status: pred={res['status']} actual={gt.get('status')}")
        if res["review_reason"] != gt.get("review_reason"):
            diffs.append(f"reason: pred={res['review_reason']} actual={gt.get('review_reason')}")
        if set(res["defect_fields"]) != set(gt.get("defect_fields", [])):
            diffs.append(f"defect_fields: pred={res['defect_fields']} actual={gt.get('defect_fields')}")

        if diffs:
            mismatches_recorded.append((eid, diffs))

    # Run official scoring
    scores = scoring.score_all(ground_truth, submission)

    print("\n" + "=" * 62)
    print("  SDOC HACKATHON EVALUATION RESULTS")
    print(f"  Total Emails: {len(submission)}")
    print("=" * 62)

    s1 = scores["stage1"]
    print("\nSTAGE 1 · Email classification")
    print(f"  Accuracy:  {s1['accuracy']:.4f}")
    print(f"  Macro-F1:  {s1['macro_f1']:.4f}")

    s3 = scores["stage3"]
    print("\nSTAGE 3 · BL-vs-SI comparison")
    print(f"  Defect Recall:     {s3['defect_recall']:.4f}")
    print(f"  Defect Precision:  {s3['defect_precision']:.4f}")
    print(f"  Defect F1:         {s3['defect_f1']:.4f}")
    print(f"  Field F1:          {s3['field_f1']:.4f}")
    print(f"  Exact-match Rate:  {s3['exact_match_rate']:.4f}")

    rel = scores["reliability"]
    print("\nRELIABILITY · Escalate what you can't decide")
    print(f"  Escalation Recall:     {rel['escalation_recall']:.4f}")
    print(f"  Escalation Precision:  {rel['escalation_precision']:.4f}")
    print(f"  Escalation F1:         {rel['escalation_f1']:.4f}")
    print(f"  Gold Needs Review: {rel['gold_review']}  |  Flagged: {rel['pred_review']}")
    for rname, d in rel["per_reason"].items():
        print(f"    {rname:<20} {d['caught']}/{d['total']} escalated")

    e2e = scores["end_to_end"]
    print("\nEND-TO-END · The headline metric")
    print(f"  Caught: {e2e['success']}/{e2e['total']} defect emails")
    print(f"  Success Rate: {e2e['rate']:.4f}")

    print("\n" + "-" * 62)
    print(f"  FINAL WEIGHTED SCORE: {scores['final_score']:.4f}")
    print("-" * 62)

    if mismatches_recorded:
        print(f"\nDiscrepancies found with ground truth ({len(mismatches_recorded)}):")
        for eid, d in mismatches_recorded[:10]:
            print(f"  {eid}: {', '.join(d)}")

    # Save submission.json
    out_file = ROOT / "submission.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(submission, f, indent=2)
    print(f"\nSaved submission to {out_file}")

    return scores


if __name__ == "__main__":
    evaluate()
