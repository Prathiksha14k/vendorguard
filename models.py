from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Vendor(db.Model):
    __tablename__ = "vendor"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    category = db.Column(db.String(100), nullable=False)  # e.g. Cloud Provider, MSP, Contractor
    contact_email = db.Column(db.String(150))

    contract_start = db.Column(db.Date)
    contract_end = db.Column(db.Date)

    # Risk input scores (1-10 each)
    data_sensitivity = db.Column(db.Integer, default=1)
    access_scope = db.Column(db.Integer, default=1)
    compliance_gaps = db.Column(db.Integer, default=1)
    financial_health = db.Column(db.Integer, default=10)  # 10 = healthiest

    last_assessment_date = db.Column(db.Date)

    # Computed fields (filled in by risk_engine.py)
    risk_score = db.Column(db.Float, default=0.0)
    risk_tier = db.Column(db.String(20), default="Low")  # Low / Medium / High

    # --- New fields from sample_data CSVs ---
    annual_spend = db.Column(db.Float)
    breach_count = db.Column(db.Integer, default=0)
    csv_risk_score = db.Column(db.Float)      # their original pre-computed score
    csv_risk_level = db.Column(db.String(20)) # their original Low/Medium/High label
    notes = db.Column(db.Text)

    # --- Ground truth label fields (from vendor_labels.csv) ---
    is_anomaly = db.Column(db.Boolean, default=False)
    anomaly_type = db.Column(db.String(100))
    label_severity = db.Column(db.String(20))
    expired_certifications = db.Column(db.Text)
    explanation = db.Column(db.Text)


# --- OUR model's own predictions (not the ground truth) ---
    predicted_anomaly = db.Column(db.Boolean, default=False)
    predicted_anomaly_type = db.Column(db.String(50))
    predicted_severity = db.Column(db.String(20))
    recommended_action = db.Column(db.Text)


    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships - lets us do vendor.breaches, vendor.certifications, etc.
    breaches = db.relationship("BreachEvent", backref="vendor", lazy=True, cascade="all, delete-orphan")
    certifications = db.relationship("Certification", backref="vendor", lazy=True, cascade="all, delete-orphan")
    alerts = db.relationship("Alert", backref="vendor", lazy=True, cascade="all, delete-orphan")
    score_history = db.relationship("RiskScoreHistory", backref="vendor", lazy=True, cascade="all, delete-orphan")
    remediation_items = db.relationship("RemediationItem", backref="vendor", lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "contact_email": self.contact_email,
            "contract_start": self.contract_start.isoformat() if self.contract_start else None,
            "contract_end": self.contract_end.isoformat() if self.contract_end else None,
            "data_sensitivity": self.data_sensitivity,
            "access_scope": self.access_scope,
            "compliance_gaps": self.compliance_gaps,
            "financial_health": self.financial_health,
            "last_assessment_date": self.last_assessment_date.isoformat() if self.last_assessment_date else None,
            "risk_score": self.risk_score,
            "risk_tier": self.risk_tier,
        }


class BreachEvent(db.Model):
    __tablename__ = "breach_event"

    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), nullable=False)

    date_occurred = db.Column(db.Date, nullable=False)
    severity = db.Column(db.Integer, default=1)  # 1-10
    description = db.Column(db.Text)
    points_assigned = db.Column(db.Float, default=0.0)  # calculated by risk_engine.py

    def to_dict(self):
        return {
            "id": self.id,
            "vendor_id": self.vendor_id,
            "date_occurred": self.date_occurred.isoformat() if self.date_occurred else None,
            "severity": self.severity,
            "description": self.description,
            "points_assigned": self.points_assigned,
        }


class Certification(db.Model):
    __tablename__ = "certification"

    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), nullable=False)

    cert_type = db.Column(db.String(50), nullable=False)  # SOC2, ISO27001, GDPR_DPA, PCI_DSS
    status = db.Column(db.String(20), default="Active")  # Active / Expired / Pending
    issue_date = db.Column(db.Date)
    expiry_date = db.Column(db.Date)

    def to_dict(self):
        return {
            "id": self.id,
            "vendor_id": self.vendor_id,
            "cert_type": self.cert_type,
            "status": self.status,
            "issue_date": self.issue_date.isoformat() if self.issue_date else None,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
        }


class Alert(db.Model):
    __tablename__ = "alert"

    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), nullable=False)

    alert_type = db.Column(db.String(50), nullable=False)
    # contract_expiring / cert_expiring / assessment_overdue / breach_detected
    message = db.Column(db.String(300))
    due_date = db.Column(db.Date)
    status = db.Column(db.String(20), default="Open")  # Open / Resolved
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "vendor_id": self.vendor_id,
            "alert_type": self.alert_type,
            "message": self.message,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "status": self.status,
        }


class RiskScoreHistory(db.Model):
    __tablename__ = "risk_score_history"

    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), nullable=False)

    score = db.Column(db.Float, nullable=False)
    tier = db.Column(db.String(20), nullable=False)
    recorded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "vendor_id": self.vendor_id,
            "score": self.score,
            "tier": self.tier,
            "recorded_at": self.recorded_at.isoformat() if self.recorded_at else None,
        }


class RemediationItem(db.Model):
    __tablename__ = "remediation_item"

    id = db.Column(db.Integer, primary_key=True)
    vendor_id = db.Column(db.Integer, db.ForeignKey("vendor.id"), nullable=False)

    action_item = db.Column(db.String(300), nullable=False)
    status = db.Column(db.String(20), default="Open")  # Open / In Progress / Resolved
    due_date = db.Column(db.Date)

    def to_dict(self):
        return {
            "id": self.id,
            "vendor_id": self.vendor_id,
            "action_item": self.action_item,
            "status": self.status,
            "due_date": self.due_date.isoformat() if self.due_date else None,
        }