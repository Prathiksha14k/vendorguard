import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, send_file
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from models import db, Vendor, BreachEvent, Certification, Alert, RiskScoreHistory, RemediationItem
from risk_engine import recalculate_and_log, generate_alerts

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///vendorguard.db"
app.config["SECRET_KEY"] = "dev-secret-key"
db.init_app(app)

with app.app_context():
    db.create_all()
    generate_alerts()


# ---------- helper ----------
def parse_date(value):
    """Turns a text date like '2026-04-15' from a form into a real date object."""
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


# ---------- DASHBOARD ----------
@app.route("/")
def dashboard():
    query = Vendor.query

    search = request.args.get("search", "")
    tier = request.args.get("tier", "")
    category = request.args.get("category", "")

    if search:
        query = query.filter(Vendor.name.ilike(f"%{search}%"))
    if tier:
        query = query.filter(Vendor.risk_tier == tier)
    if category:
        query = query.filter(Vendor.category.ilike(f"%{category}%"))

    vendors = query.order_by(Vendor.risk_score.desc()).all()

    all_vendors = Vendor.query.all()
    total = len(all_vendors)
    low_count = len([v for v in all_vendors if v.risk_tier == "Low"])
    med_count = len([v for v in all_vendors if v.risk_tier == "Medium"])
    high_count = len([v for v in all_vendors if v.risk_tier == "High"])

    categories = sorted(set(v.category for v in all_vendors if v.category))

    return render_template(
        "dashboard.html",
        vendors=vendors,
        total=total,
        low_count=low_count,
        med_count=med_count,
        high_count=high_count,
        categories=categories,
        search=search,
        tier=tier,
        category=category,
    )


# ---------- VENDOR DETAIL ----------
@app.route("/vendor/<int:vendor_id>")
def vendor_detail(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)

    # Bar chart: score breakdown
    breakdown_fig = go.Figure(data=[go.Bar(
        x=["Sensitivity x Access", "Compliance Gaps", "Breach History", "Financial Penalty"],
        y=[
            round((vendor.data_sensitivity * vendor.access_scope) / 10, 2),
            vendor.compliance_gaps,
            sum(b.points_assigned for b in vendor.breaches),
            10 - vendor.financial_health,
        ],
        marker_color=["#1A2B4C", "#F1C40F", "#E74C3C", "#2ECC71"]
    )])
    breakdown_fig.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=300)
    breakdown_chart = breakdown_fig.to_html(full_html=False, include_plotlyjs="cdn")

    # Line chart: score history
    history = sorted(vendor.score_history, key=lambda h: h.recorded_at)
    history_fig = px.line(
        x=[h.recorded_at for h in history],
        y=[h.score for h in history],
        labels={"x": "Date", "y": "Risk Score"},
        markers=True,
    )
    history_fig.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=300)
    history_chart = history_fig.to_html(full_html=False, include_plotlyjs=False)

    return render_template(
        "vendor_detail.html",
        vendor=vendor,
        breakdown_chart=breakdown_chart,
        history_chart=history_chart,
    )


# ---------- ADD / EDIT VENDOR ----------
@app.route("/vendor/new", methods=["GET", "POST"])
def vendor_new():
    if request.method == "POST":
        vendor = Vendor(
            name=request.form["name"],
            category=request.form["category"],
            contact_email=request.form.get("contact_email"),
            contract_start=parse_date(request.form.get("contract_start")),
            contract_end=parse_date(request.form.get("contract_end")),
            data_sensitivity=int(request.form.get("data_sensitivity", 1)),
            access_scope=int(request.form.get("access_scope", 1)),
            compliance_gaps=int(request.form.get("compliance_gaps", 1)),
            financial_health=int(request.form.get("financial_health", 10)),
            last_assessment_date=parse_date(request.form.get("last_assessment_date")),
        )
        db.session.add(vendor)
        db.session.commit()

        recalculate_and_log(vendor)
        generate_alerts()

        return redirect(url_for("vendor_detail", vendor_id=vendor.id))

    return render_template("vendor_form.html", vendor=None)


@app.route("/vendor/<int:vendor_id>/edit", methods=["GET", "POST"])
def vendor_edit(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)

    if request.method == "POST":
        vendor.name = request.form["name"]
        vendor.category = request.form["category"]
        vendor.contact_email = request.form.get("contact_email")
        vendor.contract_start = parse_date(request.form.get("contract_start"))
        vendor.contract_end = parse_date(request.form.get("contract_end"))
        vendor.data_sensitivity = int(request.form.get("data_sensitivity", 1))
        vendor.access_scope = int(request.form.get("access_scope", 1))
        vendor.compliance_gaps = int(request.form.get("compliance_gaps", 1))
        vendor.financial_health = int(request.form.get("financial_health", 10))
        vendor.last_assessment_date = parse_date(request.form.get("last_assessment_date"))

        db.session.commit()
        recalculate_and_log(vendor)
        generate_alerts()

        return redirect(url_for("vendor_detail", vendor_id=vendor.id))

    return render_template("vendor_form.html", vendor=vendor)


@app.route("/vendor/<int:vendor_id>/delete", methods=["POST"])
def vendor_delete(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)
    db.session.delete(vendor)
    db.session.commit()
    return redirect(url_for("dashboard"))


# ---------- ALERTS ----------
@app.route("/alerts")
def alerts_page():
    generate_alerts()

    filter_type = request.args.get("type", "")

    query = Alert.query.filter_by(status="Open")
    if filter_type:
        query = query.filter_by(alert_type=filter_type)

    # Order: breaches first (most urgent), then cert/contract expiring, then overdue assessments
    type_priority = {
        "breach_detected": 0,
        "contract_expiring": 1,
        "cert_expiring": 2,
        "assessment_overdue": 3,
    }
    all_alerts = query.all()
    all_alerts.sort(key=lambda a: (type_priority.get(a.alert_type, 9), a.due_date or date.min))

    # Counts per type, for the filter buttons
    type_counts = {
        "breach_detected": len([a for a in all_alerts if a.alert_type == "breach_detected"]),
        "contract_expiring": len([a for a in all_alerts if a.alert_type == "contract_expiring"]),
        "cert_expiring": len([a for a in all_alerts if a.alert_type == "cert_expiring"]),
        "assessment_overdue": len([a for a in all_alerts if a.alert_type == "assessment_overdue"]),
    }

    return render_template("alerts.html", alerts=all_alerts, filter_type=filter_type, type_counts=type_counts)

@app.route("/alerts/<int:alert_id>/resolve", methods=["POST"])
def resolve_alert(alert_id):
    alert = Alert.query.get_or_404(alert_id)
    alert.status = "Resolved"
    db.session.commit()
    return redirect(url_for("alerts_page"))


# ---------- COMPLIANCE ----------
@app.route("/compliance")
def compliance_page():
    certs = Certification.query.all()
    today = date.today()
    return render_template("compliance.html", certs=certs, today=today)


# ---------- REPORTS ----------
@app.route("/reports")
def reports_page():
    vendors = Vendor.query.all()
    total = len(vendors)
    low_count = len([v for v in vendors if v.risk_tier == "Low"])
    med_count = len([v for v in vendors if v.risk_tier == "Medium"])
    high_count = len([v for v in vendors if v.risk_tier == "High"])

    # Ranked risk register: every flagged vendor, sorted by severity then score
    severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    flagged = [v for v in vendors if v.predicted_anomaly]
    flagged_sorted = sorted(
        flagged,
        key=lambda v: (severity_order.get(v.predicted_severity, 4), -v.risk_score)
    )

    all_certs = Certification.query.all()
    active_certs = len([c for c in all_certs if c.status == "Active"])
    cert_coverage = round((active_certs / len(all_certs)) * 100, 1) if all_certs else 0

    return render_template(
        "reports.html",
        total=total,
        low_count=low_count,
        med_count=med_count,
        high_count=high_count,
        flagged_sorted=flagged_sorted,
        cert_coverage=cert_coverage,
        report_date=date.today(),
    )
@app.route("/framework")
def framework_page():
    return render_template("framework.html")


@app.route("/integrations")
def integrations_page():
    return render_template("integrations.html")


@app.route("/vendor/<int:vendor_id>/remediation/new", methods=["POST"])
def add_remediation(vendor_id):
    vendor = Vendor.query.get_or_404(vendor_id)

    item = RemediationItem(
        vendor_id=vendor.id,
        action_item=request.form["action_item"],
        status=request.form.get("status", "Open"),
        due_date=parse_date(request.form.get("due_date")),
    )
    db.session.add(item)
    db.session.commit()

    return redirect(url_for("vendor_detail", vendor_id=vendor.id))


@app.route("/remediation/<int:item_id>/update", methods=["POST"])
def update_remediation(item_id):
    item = RemediationItem.query.get_or_404(item_id)
    item.status = request.form["status"]
    db.session.commit()
    return redirect(url_for("vendor_detail", vendor_id=item.vendor_id))


# ---------- IMPORT (CSV) ----------
@app.route("/import", methods=["GET", "POST"])
def import_page():
    if request.method == "POST":
        file = request.files.get("csv_file")
        if file:
            df = pd.read_csv(file)

            for _, row in df.iterrows():
                vendor = Vendor(
                    name=row.get("name"),
                    category=row.get("category"),
                    contact_email=row.get("contact_email"),
                    contract_start=parse_date(str(row.get("contract_start"))) if pd.notna(row.get("contract_start")) else None,
                    contract_end=parse_date(str(row.get("contract_end"))) if pd.notna(row.get("contract_end")) else None,
                    data_sensitivity=int(row.get("data_sensitivity", 1)),
                    access_scope=int(row.get("access_scope", 1)),
                    compliance_gaps=int(row.get("compliance_gaps", 1)),
                    financial_health=int(row.get("financial_health", 10)),
                )
                db.session.add(vendor)
                db.session.commit()
                recalculate_and_log(vendor)

            generate_alerts()
            return redirect(url_for("dashboard"))

    return render_template("import.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)