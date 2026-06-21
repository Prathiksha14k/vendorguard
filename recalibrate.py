"""
Re-applies the NEW risk tier thresholds to all existing vendors,
without re-importing from CSV. Run this any time you change the
cutoffs in get_risk_tier().
"""

from app import app
from models import db, Vendor
from risk_engine import get_risk_tier

with app.app_context():
    vendors = Vendor.query.all()
    changed = 0

    for vendor in vendors:
        new_tier = get_risk_tier(vendor.risk_score)
        if new_tier != vendor.risk_tier:
            vendor.risk_tier = new_tier
            changed += 1

    db.session.commit()
    print(f"✅ Re-tiered {changed} vendors out of {len(vendors)} total.")