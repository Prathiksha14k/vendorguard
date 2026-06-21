"""
One-time script to load sample_data/vendor_registry.csv and
sample_data/vendor_labels.csv into the VendorGuard database.

Run this with:  python load_sample_data.py
"""

import pandas as pd
from datetime import datetime
from app import app
from models import db, Vendor, Certification, BreachEvent
from risk_engine import recalculate_and_log


def parse_date(value):
    """Safely turns a CSV date string into a real date. Returns None if it can't."""
    if pd.isna(value) or value in ("", None):
        return None
    value = str(value).strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    print(f"⚠️  Could not parse date: '{value}' — leaving blank.")
    return None


def parse_bool_like(value):
    """
    Turns Yes/No, True/False, Y/N, 1/0 into a real Python bool.
    Returns False if it's empty or unrecognized.
    """
    if pd.isna(value):
        return False
    text = str(value).strip().lower()
    return text in ("yes", "y", "true", "1", "active", "valid", "compliant")


def parse_financial_rating(value):
    """
    Converts financial_rating into our 1-10 'financial_health' scale.
    Handles BOTH letter grades (A/B/C/D/F) and numbers (1-10).
    """
    if pd.isna(value):
        return 5  # neutral default if missing

    text = str(value).strip().upper()

    letter_map = {
        "A": 10, "A+": 10, "A-": 9,
        "B": 7, "B+": 8, "B-": 6,
        "C": 5, "C+": 6, "C-": 4,
        "D": 3, "D+": 4, "D-": 2,
        "F": 1,
    }
    if text in letter_map:
        return letter_map[text]

    try:
        num = float(text)
        if num <= 10:
            return round(num)
        else:
            # if it's something like a 0-100 financial score, scale it down
            return round(num / 10)
    except ValueError:
        print(f"⚠️  Unrecognized financial_rating: '{value}' — defaulting to 5.")
        return 5

def parse_level_to_number(value, default=5):
    """
    Converts text risk levels like HIGH/MEDIUM/LOW into a 1-10 number.
    Also handles if the value is already a number.
    """
    if pd.isna(value):
        return default

    text = str(value).strip().upper()

    level_map = {
        "VERY LOW": 1,
        "LOW": 3,
        "MEDIUM": 5,
        "MED": 5,
        "MODERATE": 5,
        "HIGH": 8,
        "VERY HIGH": 10,
        "CRITICAL": 10,
    }
    if text in level_map:
        return level_map[text]

    try:
        return round(float(text))
    except ValueError:
        print(f"⚠️  Unrecognized level value: '{value}' — defaulting to {default}.")
        return default
def compute_compliance_gaps(row):
    """
    We don't have a direct 'compliance_gaps' column in the CSV,
    so we BUILD it from how many certifications are MISSING.
    Each missing/expired cert adds points (max 10).
    """
    gaps = 0
    if not parse_bool_like(row.get("soc2_type2")):
        gaps += 4
    if not parse_bool_like(row.get("iso27001")):
        gaps += 3
    if not parse_bool_like(row.get("gdpr_dpa")):
        gaps += 3
    return min(gaps, 10)


def load_registry_and_labels():
    registry_df = pd.read_csv("sample_data/vendor_registry.csv")
    labels_df = pd.read_csv("sample_data/vendor_labels.csv")

    # merge the two files together on vendor_id, so each row has BOTH
    # the vendor's real data AND its ground-truth label info.
    merged_df = registry_df.merge(labels_df, on="vendor_id", how="left")

    print(f"Loaded {len(registry_df)} vendors from registry, "
          f"{len(labels_df)} labels, merged into {len(merged_df)} rows.")

    created_count = 0

    for _, row in merged_df.iterrows():
        vendor = Vendor(
            name=row.get("vendor_name"),
            category=row.get("category"),
            contract_start=parse_date(row.get("contract_start_date")),
            contract_end=parse_date(row.get("contract_end_date")),

            data_sensitivity=parse_level_to_number(row.get("data_sensitivity")),
            access_scope=parse_level_to_number(row.get("access_scope")),
            compliance_gaps=compute_compliance_gaps(row),
            financial_health=parse_financial_rating(row.get("financial_rating")),

            annual_spend=float(row["annual_spend"]) if pd.notna(row.get("annual_spend")) else None,
            breach_count=int(row["breach_count"]) if pd.notna(row.get("breach_count")) else 0,
            csv_risk_score=float(row["risk_score"]) if pd.notna(row.get("risk_score")) else None,
            csv_risk_level=row.get("risk_level"),
            notes=row.get("notes"),

            last_assessment_date=parse_date(row.get("assessment_date")),

            is_anomaly=parse_bool_like(row.get("is_anomaly")),
            anomaly_type=row.get("anomaly_type") if pd.notna(row.get("anomaly_type")) else None,
            label_severity=row.get("severity") if pd.notna(row.get("severity")) else None,
            expired_certifications=row.get("expired_certifications") if pd.notna(row.get("expired_certifications")) else None,
            explanation=row.get("explanation") if pd.notna(row.get("explanation")) else None,
        )

        db.session.add(vendor)
        db.session.commit()  # commit now so vendor.id exists for certs/breaches below

        # --- Add certifications as separate rows ---
        if parse_bool_like(row.get("soc2_type2")):
            db.session.add(Certification(
                vendor_id=vendor.id,
                cert_type="SOC2_Type2",
                status="Active",
                expiry_date=parse_date(row.get("soc2_expiry")),
            ))

        if parse_bool_like(row.get("iso27001")):
            db.session.add(Certification(
                vendor_id=vendor.id,
                cert_type="ISO27001",
                status="Active",
                expiry_date=parse_date(row.get("iso27001_expiry")),
            ))

        if parse_bool_like(row.get("gdpr_dpa")):
            db.session.add(Certification(
                vendor_id=vendor.id,
                cert_type="GDPR_DPA",
                status="Active",
                expiry_date=None,
            ))

        # --- Add a breach event if breach_count > 0 ---
        breach_count = int(row["breach_count"]) if pd.notna(row.get("breach_count")) else 0
        if breach_count > 0:
            db.session.add(BreachEvent(
                vendor_id=vendor.id,
                date_occurred=parse_date(row.get("assessment_date")) or datetime.utcnow().date(),
                severity=min(breach_count * 2, 10),
                description=f"{breach_count} known breach(es) on file for this vendor.",
            ))

        db.session.commit()

        # --- Calculate OUR risk score using risk_engine.py and log it ---
        recalculate_and_log(vendor)

        created_count += 1
        if created_count % 50 == 0:
            print(f"...loaded {created_count} vendors so far")

    print(f"✅ Done. {created_count} vendors loaded into the database.")


if __name__ == "__main__":
    with app.app_context():
        load_registry_and_labels()