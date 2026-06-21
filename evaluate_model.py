"""
Runs the official self-evaluation from the challenge brief,
using OUR predicted_anomaly field against their ground truth.
"""

from sklearn.metrics import precision_score, recall_score
from app import app
from models import Vendor

with app.app_context():
    vendors = Vendor.query.all()

    y_true = [1 if v.is_anomaly else 0 for v in vendors]
    y_pred = [1 if v.predicted_anomaly else 0 for v in vendors]

    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)

    print(f"Precision: {precision:.2%}")
    print(f"Recall:    {recall:.2%}")

    # Priority check: CRITICAL vendors should ALWAYS be caught
    critical_vendors = [v for v in vendors if v.label_severity == "CRITICAL"]
    if critical_vendors:
        caught = [v for v in critical_vendors if v.predicted_anomaly]
        critical_recall = len(caught) / len(critical_vendors)
        print(f"CRITICAL vendor recall: {critical_recall:.2%}  ({len(caught)}/{len(critical_vendors)} caught)")
    else:
        print("No CRITICAL vendors found in ground truth to check.")