from app import app
from models import db, Vendor
from anomaly_classifier import classify_all_vendors

with app.app_context():
    classify_all_vendors(db, Vendor)