from datetime import date
from models import db, Vendor, BreachEvent, RiskScoreHistory, Certification, Alert


def calculate_breach_history(vendor):
    """
    Looks at every breach a vendor had.
    Recent breaches count MORE than old breaches.
    Returns one total number = "Breach_History" score.
    """
    total = 0.0
    today = date.today()

    for breach in vendor.breaches:
        if not breach.date_occurred:
            continue

        years_ago = (today - breach.date_occurred).days / 365.0

        if years_ago < 1:
            recency_weight = 1.0      # happened less than a year ago = big deal
        elif years_ago < 3:
            recency_weight = 0.6      # 1-3 years ago = medium deal
        else:
            recency_weight = 0.3      # older than 3 years = smaller deal

        points = breach.severity * recency_weight
        breach.points_assigned = points  # save it back onto the breach row
        total += points

    return total


def calculate_risk_score(vendor):
    """
    The main formula. Plugs in the vendor's numbers and spits out one risk score.

    Vendor_Risk = (Data_Sensitivity * Access_Scope / 10)
                  + Compliance_Gaps
                  + Breach_History
                  + (10 - Financial_Health)
    """
    sensitivity_access_part = (vendor.data_sensitivity * vendor.access_scope) / 10
    compliance_part = vendor.compliance_gaps
    breach_part = calculate_breach_history(vendor)
    financial_part = 10 - vendor.financial_health  # worse financial health = more risk

    total_score = sensitivity_access_part + compliance_part + breach_part + financial_part

    return round(total_score, 2)


def get_risk_tier(score):
    """
    Turns a number into a traffic light color name.
    Thresholds calibrated from the actual vendor dataset's score
    distribution (60th percentile and 90th percentile), so roughly
    60% of vendors land Low, 30% Medium, 10% High.
    """
    if score < 10.5:
        return "Low"
    elif score < 15.0:
        return "Medium"
    else:
        return "High"


def recalculate_and_log(vendor):
    """
    The main function you call whenever a vendor is added or changed.
    1. Calculates the new score.
    2. Saves it onto the vendor.
    3. Writes one line into the history table, so we can see the score over time.
    """
    score = calculate_risk_score(vendor)
    tier = get_risk_tier(score)

    vendor.risk_score = score
    vendor.risk_tier = tier

    history_row = RiskScoreHistory(
        vendor_id=vendor.id,
        score=score,
        tier=tier
    )
    db.session.add(history_row)
    db.session.commit()

    return score, tier


def generate_alerts():
    """
    Checks EVERY vendor for things that need attention, and creates
    Alert rows for anything urgent. Skips creating duplicate alerts
    if an open one already exists for the same vendor + type.
    """
    today = date.today()
    vendors = Vendor.query.all()

    for vendor in vendors:
        # --- 1. Contract expiring within 60 days ---
        if vendor.contract_end:
            days_left = (vendor.contract_end - today).days
            if 0 <= days_left <= 60:
                _create_alert_if_not_exists(
                    vendor.id,
                    "contract_expiring",
                    f"Contract for {vendor.name} expires in {days_left} days",
                    vendor.contract_end
                )

        # --- 2. Certification expiring within 60 days ---
        for cert in vendor.certifications:
            if cert.expiry_date:
                days_left = (cert.expiry_date - today).days
                if 0 <= days_left <= 60:
                    _create_alert_if_not_exists(
                        vendor.id,
                        "cert_expiring",
                        f"{cert.cert_type} for {vendor.name} expires in {days_left} days",
                        cert.expiry_date
                    )

        # --- 3. Assessment overdue (more than 365 days since last check) ---
        if vendor.last_assessment_date:
            days_since = (today - vendor.last_assessment_date).days
            if days_since > 365:
                _create_alert_if_not_exists(
                    vendor.id,
                    "assessment_overdue",
                    f"{vendor.name} has not been re-assessed in {days_since} days",
                    today
                )

        # --- 4. Breach detected (any breach in the last 90 days) ---
        for breach in vendor.breaches:
            if breach.date_occurred:
                days_since = (today - breach.date_occurred).days
                if 0 <= days_since <= 90:
                    _create_alert_if_not_exists(
                        vendor.id,
                        "breach_detected",
                        f"Recent breach detected for {vendor.name} ({breach.date_occurred})",
                        breach.date_occurred
                    )

    db.session.commit()


def _create_alert_if_not_exists(vendor_id, alert_type, message, due_date):
    """
    Helper: only creates a new alert if there isn't already an
    OPEN alert of the same type for the same vendor.
    """
    existing = Alert.query.filter_by(
        vendor_id=vendor_id,
        alert_type=alert_type,
        status="Open"
    ).first()

    if not existing:
        new_alert = Alert(
            vendor_id=vendor_id,
            alert_type=alert_type,
            message=message,
            due_date=due_date,
            status="Open"
        )
        db.session.add(new_alert)
        db.session.commit()

def recommend_sla_terms(vendor):
    """
    Suggests contract/SLA terms based on the vendor's risk tier.
    This is what a procurement/legal team would use when negotiating
    or renewing a vendor contract.
    """
    if vendor.risk_tier == "High":
        return [
            "Require 24-hour breach notification clause (stricter than standard 72-hour GDPR baseline)",
            "Mandate quarterly security attestation, not annual",
            "Require right-to-audit clause with on-site inspection rights",
            "Cap contract term to 12 months to allow frequent re-evaluation",
        ]
    elif vendor.risk_tier == "Medium":
        return [
            "Require 48-hour breach notification clause",
            "Mandate annual SOC 2 / ISO 27001 renewal proof before contract renewal",
            "Include data deletion and return clause upon contract termination",
        ]
    else:
        return [
            "Standard 72-hour breach notification clause (GDPR baseline) is sufficient",
            "Annual compliance check-in is sufficient given low risk profile",
        ]