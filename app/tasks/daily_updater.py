"""
Daily Scheduled Tasks  —  FraudGuard AI
=========================================
Uses APScheduler (BackgroundScheduler) to run maintenance jobs on a schedule.

Jobs registered here:
  • ofac_daily_update  — 02:00 every day
    Downloads the latest OFAC SDN list and updates the database.

The scheduler is started by the Flask application factory (app/__init__.py)
via start_scheduler(app).  It runs in a daemon thread so it stops cleanly
when the server process exits.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

# Module-level scheduler singleton
_scheduler = None


def start_scheduler(app) -> None:
    """
    Initialise and start the APScheduler BackgroundScheduler.
    Call once from the Flask application factory.
    """
    global _scheduler

    # Guard: don't start a second scheduler when Flask reloader forks
    if _scheduler is not None:
        return

    # Guard: Flask debug reloader spawns two processes; only start in the
    # child/main worker (WERKZEUG_RUN_MAIN == 'true') or in production.
    if os.environ.get('WERKZEUG_RUN_MAIN') == 'false':
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron         import CronTrigger
    except ImportError:
        logger.warning(
            "[Scheduler] APScheduler not installed — daily OFAC updates disabled.\n"
            "            Install with:  pip install APScheduler==3.10.4"
        )
        return

    _scheduler = BackgroundScheduler(
        daemon=True,
        job_defaults={
            'coalesce':           True,   # collapse missed runs into one
            'max_instances':      1,      # don't overlap
            'misfire_grace_time': 3600,   # allow 1-hour grace for missed runs
        },
    )

    # ── Job 1: OFAC SDN list update — runs at 02:00 daily ────────────────────
    _scheduler.add_job(
        func       = _run_ofac_update,
        trigger    = CronTrigger(hour=2, minute=0),
        args       = [app],
        id         = 'ofac_daily_update',
        name       = 'OFAC Sanctions List Daily Update',
        replace_existing=True,
    )

    # ── Job 2: (Optional) run once on startup if DB is empty ──────────────────
    _scheduler.add_job(
        func       = _initial_ofac_seed,
        trigger    = 'date',              # run once immediately
        args       = [app],
        id         = 'ofac_initial_seed',
        name       = 'OFAC Initial Seed on Startup',
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "[Scheduler] Started — OFAC update scheduled daily at 02:00. "
        "Next run: %s",
        _scheduler.get_job('ofac_daily_update').next_run_time,
    )


def stop_scheduler() -> None:
    """Stop the scheduler gracefully (called on app teardown)."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[Scheduler] Stopped.")
    _scheduler = None


def _run_ofac_update(app) -> None:
    """APScheduler job: download and refresh the OFAC SDN list."""
    logger.info("[Scheduler] Running OFAC daily update at %s …", datetime.utcnow().isoformat())
    try:
        from app.services.ofac_service import update_sanctions_list
        result = update_sanctions_list(app)
        if result.get('skipped'):
            logger.info("[Scheduler] OFAC update skipped: %s", result.get('reason'))
        else:
            logger.info(
                "[Scheduler] OFAC update complete — %d entries stored.",
                result.get('total', 0),
            )
    except Exception as exc:
        logger.error("[Scheduler] OFAC update FAILED: %s", exc, exc_info=True)


def _initial_ofac_seed(app) -> None:
    """
    On first startup: if the OFAC table is empty, seed it with the built-in
    sample list (so the system works without an internet connection).
    A full download will happen at 02:00 on the first night.
    """
    try:
        from app.models.models import OFACEntry
        with app.app_context():
            count = OFACEntry.query.count()
            if count == 0:
                logger.info("[Scheduler] OFAC table empty — seeding built-in sample list …")
                from app.services.ofac_service import BUILTIN_SDN_SAMPLE, _normalise
                from app.models.models import db, OFACUpdate

                entries = [
                    OFACEntry(
                        sdn_name      = name,
                        sdn_name_norm = _normalise(name),
                        sdn_type      = stype,
                        program       = prog,
                        remarks       = 'Built-in sample — updated at 02:00',
                    )
                    for name, stype, prog in BUILTIN_SDN_SAMPLE
                ]
                db.session.bulk_save_objects(entries)
                record = OFACUpdate(
                    status        = 'success',
                    entries_added = len(entries),
                    entries_total = len(entries),
                )
                db.session.add(record)
                db.session.commit()
                logger.info(
                    "[Scheduler] Seeded %d built-in OFAC entries. "
                    "Full list downloads tonight at 02:00.", len(entries)
                )
            else:
                logger.info("[Scheduler] OFAC table has %d entries — no seed needed.", count)
    except Exception as exc:
        logger.warning("[Scheduler] Initial OFAC seed failed: %s", exc)


def get_scheduler_info() -> dict:
    """Return current scheduler status (for the gateway health endpoint)."""
    if _scheduler is None:
        return {'running': False, 'jobs': []}
    if not _scheduler.running:
        return {'running': False, 'jobs': []}

    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            'id':       job.id,
            'name':     job.name,
            'next_run': job.next_run_time.isoformat() if job.next_run_time else None,
        })
    return {'running': True, 'jobs': jobs}
