"""
Classifies each vendor into ONE of the 7 official anomaly types
defined by the challenge brief, with severity + recommended action.
This is OUR model's prediction — separate from the ground truth
labels in vendor_labels.csv.
"""

from datetime import date


def classify_vendor(vendor):
    """
    Checks a vendor against the 7 rules, in priority order
    (CRITICAL checked first, LOW checked last).
    Returns (is_anomaly: bool, anomaly_type: str|None, severity: str|None, action: str)
    """
    today = date.today()
    has_sensitive_access = vendor.data_sensitivity >= 6 or vendor.access_scope >= 6

    recent_breach = False
    breach_days_ago = None
    for b in vendor.breaches:
        if b.date_occurred:
            days_ago = (today - b.date_occurred).days
            if breach_days_ago is None or days_ago < breach_days_ago:
                breach_days_ago = days_ago
            if days_ago <= 365:
                recent_breach = True

    # --- RULE 1: BREACHED_VENDOR_HIGH_ACCESS (CRITICAL) ---
    if recent_breach and has_sensitive_access:
        return True, "BREACHED_VENDOR_HIGH_ACCESS", "CRITICAL", \
            "Immediate compliance meeting required — breached vendor has sensitive data access."

    # --- RULE 2: VENDOR_UNDER_INVESTIGATION (CRITICAL) ---
    notes_text = (vendor.notes or "").lower()
    if "investigation" in notes_text or "under review" in notes_text:
        return True, "VENDOR_UNDER_INVESTIGATION", "CRITICAL", \
            "Suspend new data sharing until investigation concludes."

    # --- RULE 3: HIGH_RISK_SCORE (their scale: >80/100) ---
    if vendor.csv_risk_score is not None and vendor.csv_risk_score > 80:
        return True, "HIGH_RISK_SCORE", "HIGH", \
            "Escalate to risk committee for formal review."

    # --- RULE 4: EXPIRED_CERTIFICATION (HIGH/MEDIUM) ---
    expired_cert_found = False
    for cert in vendor.certifications:
        if cert.expiry_date and cert.expiry_date < today:
            expired_cert_found = True
    if expired_cert_found and has_sensitive_access:
        severity = "HIGH" if vendor.data_sensitivity >= 8 else "MEDIUM"
        return True, "EXPIRED_CERTIFICATION", severity, \
            "Request updated certification from vendor within 30 days."

    # --- RULE 5: RECENTLY_BREACHED_VENDOR (MEDIUM, lower scope) ---
    if recent_breach and not has_sensitive_access:
        return True, "RECENTLY_BREACHED_VENDOR", "MEDIUM", \
            "Monitor vendor remediation progress; reassess in 90 days."

    # --- RULE 6: CONTRACT_EXPIRED_ACTIVE_ACCESS (MEDIUM) ---
    if vendor.contract_end and vendor.contract_end < today:
        return True, "CONTRACT_EXPIRED_ACTIVE_ACCESS", "MEDIUM", \
            "Revoke access immediately or renew contract — orphaned access risk."

    # --- RULE 7: ELEVATED_RISK_VENDOR (LOW, their scale 65-80) ---
    if vendor.csv_risk_score is not None and 65 <= vendor.csv_risk_score <= 80:
        return True, "ELEVATED_RISK_VENDOR", "LOW", \
            "Increase monitoring frequency to quarterly."

    # --- No anomaly triggered ---
    return False, None, None, "No action needed — vendor within acceptable risk parameters."


def classify_all_vendors(db, Vendor):
    """Runs the classifier on every vendor and saves the results."""
    vendors = Vendor.query.all()
    flagged_count = 0

    for vendor in vendors:
        is_anomaly, anomaly_type, severity, action = classify_vendor(vendor)
        vendor.predicted_anomaly = is_anomaly
        vendor.predicted_anomaly_type = anomaly_type
        vendor.predicted_severity = severity
        vendor.recommended_action = action
        if is_anomaly:
            flagged_count += 1

    db.session.commit()
    print(f"✅ Classified {len(vendors)} vendors. {flagged_count} flagged as anomalies.")