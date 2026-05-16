"""
Compliance API Blueprint  —  v3 (Security-hardened)
=====================================================
OFAC sanctions screening, age-restriction monitoring,
and background scheduler management.

Routes
------
GET  /api/compliance/ofac/status          OFAC service health & counts
POST /api/compliance/ofac/check           Screen a single name
POST /api/compliance/ofac/refresh         Force SDN download     (admin only)
GET  /api/compliance/ofac/updates         Update history log
GET  /api/compliance/ofac/entries         Paginated + filtered SDN list browse
GET  /api/compliance/ofac/programs        Unique programme code list
GET  /api/compliance/age-violations       Customers with age rule violations
GET  /api/compliance/scheduler            APScheduler job status  (admin only)

Security controls:
  • Force-refresh and scheduler endpoints are admin-only
  • All exception details logged server-side, generic messages to client
  • Input validated and bounded before passing to service layer
  • Rate-limited: OFAC check 10/min, refresh 5/min
"""
import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from app.utils.security import admin_required, safe_str, safe_int

logger = logging.getLogger(__name__)

compliance_bp = Blueprint("compliance", __name__, url_prefix="/api/compliance")


# ─── OFAC Status ─────────────────────────────────────────────────────────────
@compliance_bp.get("/ofac/status")
@jwt_required()
def ofac_status():
    try:
        from app.services.ofac_service import get_status
        s = get_status()
        return jsonify({
            "service":       "OFAC SDN Screening",
            "operational":   s["total_entries"] > 0,
            "total_entries": s["total_entries"],
            "last_update":   s["last_update"],
            "last_status":   s["last_status"],
            "threshold":     s["threshold"],
        })
    except Exception:
        logger.exception('Error fetching OFAC status')
        return jsonify({"error": "Could not retrieve OFAC service status"}), 500


# ─── SDN List Browse (paginated + searchable) ─────────────────────────────────
@compliance_bp.get("/ofac/entries")
@jwt_required()
def ofac_entries():
    q        = safe_str(request.args.get("q",       ""), max_length=100)
    sdn_type = safe_str(request.args.get("type",    ""), max_length=30)
    program  = safe_str(request.args.get("program", ""), max_length=50)
    page     = safe_int(request.args.get("page",    1),  min_val=1, max_val=10_000)
    per_page = safe_int(request.args.get("per_page", 25), min_val=5, max_val=100)

    try:
        from app.services.ofac_service import search_entries
        result = search_entries(query=q, sdn_type=sdn_type, program=program,
                                page=page, per_page=per_page)
        return jsonify(result)
    except Exception:
        logger.exception('Error searching OFAC entries')
        return jsonify({"error": "Could not retrieve SDN entries"}), 500


# ─── Programme List ────────────────────────────────────────────────────────────
@compliance_bp.get("/ofac/programs")
@jwt_required()
def ofac_programs():
    try:
        from app.services.ofac_service import get_programs
        return jsonify(get_programs())
    except Exception:
        logger.exception('Error fetching OFAC programmes')
        return jsonify({"error": "Could not retrieve programme list"}), 500


# ─── Name Check ───────────────────────────────────────────────────────────────
@compliance_bp.post("/ofac/check")
@jwt_required()
def ofac_check():
    data = request.get_json(silent=True) or {}
    name = safe_str(data.get("name", ""), max_length=200)
    if not name:
        return jsonify({"error": "name is required"}), 400

    raw_threshold = data.get("threshold", 0.82)
    try:
        threshold = float(raw_threshold)
        threshold = max(0.40, min(0.99, threshold))   # clamp to safe range
    except (TypeError, ValueError):
        threshold = 0.82

    try:
        from app.services.ofac_service import check_name
        match = check_name(name, threshold=threshold)
        return jsonify({
            "queried": name,
            "matched": match is not None,
            "match":   match,
        })
    except Exception:
        logger.exception('Error performing OFAC name check for: %s', name)
        return jsonify({"error": "OFAC screening service temporarily unavailable"}), 503


# ─── Force Refresh (admin only) ───────────────────────────────────────────────
@compliance_bp.post("/ofac/refresh")
@admin_required
def ofac_refresh():
    """Force a full re-download of the OFAC SDN list — admin only."""
    try:
        from app.services.ofac_service import update_sanctions_list
        from flask import current_app
        result = update_sanctions_list(current_app._get_current_object())
        logger.info('Admin forced OFAC refresh: %s', result)
        return jsonify({"success": True, "result": result})
    except Exception:
        logger.exception('Error during forced OFAC refresh')
        return jsonify({"error": "OFAC refresh failed. Check server logs."}), 500


# ─── Update History ───────────────────────────────────────────────────────────
@compliance_bp.get("/ofac/updates")
@jwt_required()
def ofac_updates():
    try:
        from app.models.models import OFACUpdate
        updates = (OFACUpdate.query
                   .order_by(OFACUpdate.updated_at.desc())
                   .limit(20)
                   .all())
        return jsonify([{
            "id":            u.id,
            "status":        u.status,
            "entries_added": u.entries_added,
            "entries_total": u.entries_total,
            "error_message": u.error_message,
            "updated_at":    u.updated_at.isoformat() if u.updated_at else None,
        } for u in updates])
    except Exception:
        logger.exception('Error fetching OFAC update history')
        return jsonify({"error": "Could not retrieve update history"}), 500


# ─── Age Violations ───────────────────────────────────────────────────────────
@compliance_bp.get("/age-violations")
@jwt_required()
def age_violations():
    try:
        from app.models.models import Customer
        customers    = Customer.query.all()
        violations   = []
        total_checked = 0

        for c in customers:
            age = c.age
            if age is None:
                continue
            total_checked += 1
            if age < 18:
                violations.append({
                    "customer_id":  c.customer_id,
                    "name":         c.name,
                    "email":        c.email,
                    "country":      c.country,
                    "date_of_birth": str(c.date_of_birth) if c.date_of_birth else None,
                    "age":          age,
                    "violation":    "MINOR",
                    "reason":       f"Age {age} is below minimum legal age of 18",
                })
            elif age > 100:
                violations.append({
                    "customer_id":  c.customer_id,
                    "name":         c.name,
                    "email":        c.email,
                    "country":      c.country,
                    "date_of_birth": str(c.date_of_birth) if c.date_of_birth else None,
                    "age":          age,
                    "violation":    "AGE_ANOMALY",
                    "reason":       f"Age {age} exceeds 100 — possible identity fraud or data error",
                })

        return jsonify({"violations": violations, "total_checked": total_checked})
    except Exception:
        logger.exception('Error fetching age violations')
        return jsonify({"error": "Could not retrieve age violation data"}), 500


# ─── Scheduler Status (admin only) ───────────────────────────────────────────
@compliance_bp.get("/scheduler")
@admin_required
def scheduler_status():
    try:
        from app.tasks.daily_updater import get_scheduler_info
        return jsonify(get_scheduler_info())
    except Exception:
        logger.exception('Error fetching scheduler status')
        return jsonify({"error": "Could not retrieve scheduler status"}), 500
