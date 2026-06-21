🛡️ VendorGuard — Third-Party Risk Scorecard Platform

Track: Third-Party Risk & Governance
Challenge: Vendor Risk Scorecard Builder (Option B)

VendorGuard is a centralized vendor risk management platform that replaces spreadsheet-based third-party risk tracking with a transparent, formula-driven scoring engine, automated anomaly classification, continuous monitoring, and audit-ready reporting.


🚀 The Problem

Enterprises working with 1,000+ vendors (cloud providers, contractors, MSPs, payment processors, etc.) struggle to:


Consistently assess vendor risk (spreadsheet-based, inconsistent, outdated)
Answer "is this vendor compliant?" quickly during audits
Continuously monitor vendor certifications, breaches, and contract status
Respond appropriately when vendor risk changes


~60% of data breaches involve a third party — yet most vendor risk programs rely on manual, ad-hoc review.

✅ The Solution

VendorGuard provides:


A centralized vendor registry (402 vendors tracked end-to-end)
A transparent risk scoring formula combining data sensitivity, access scope, compliance gaps, breach history, and financial health
An anomaly classification engine mapping every vendor to one of 7 industry-defined risk categories with assigned severity and a recommended action — producing a ranked risk register, not a binary pass/fail list
Continuous monitoring with automated alerts for expiring contracts, expiring certifications, overdue assessments, and recent breaches
Remediation tracking so flagged issues can be logged and resolved in-platform
Risk-based SLA recommendations to support contract negotiation
Compliance framework alignment mapped explicitly to GDPR Articles 28 & 33, NIST SP 800-53 SA-9, and SOX 404


📊 Validated Results

The classification engine was evaluated against ground-truth labels using the precision/recall methodology specified in the challenge brief:

MetricResultPrecision81.89%Recall91.88%CRITICAL severity recall98.75% (79/80 caught)Risk tier distribution58% Low / 31% Medium / 11% High (closely matches the brief's reference pattern)

🧱 Tech Stack

LayerTechnologyBackendPython 3 + FlaskDatabaseSQLite (SQLAlchemy ORM)Data ProcessingPandasVisualizationPlotlyModel Evaluationscikit-learnFrontendJinja2 templates + Bootstrap 5 + Bootstrap IconsStylingCustom CSS

 Risk Scoring Formula

Vendor_Risk = (Data_Sensitivity × Access_Scope ÷ 10) + Compliance_Gaps + Breach_History + (10 − Financial_Health)

ComponentRangeDescriptionData Sensitivity1–10Does the vendor touch PII, financial, or other sensitive data?Access Scope1–10Breadth of systems accessed, read/write permissionsCompliance Gaps1–10Derived from missing SOC2 / ISO27001 / GDPR DPA certificationsBreach HistoryAdditiveSum of breach severity, weighted by recency (1.0× <1yr, 0.6× 1–3yr, 0.3× >3yr)Financial Health1–10 (10 = healthiest)Penalized as (10 − value) in the formula

Risk Tiers (calibrated via percentile analysis on the dataset):


Low: score < 10.5
Medium: 10.5 ≤ score < 15.0
High: score ≥ 15.0
