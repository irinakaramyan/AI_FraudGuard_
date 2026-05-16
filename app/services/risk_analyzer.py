"""
Risk Analyzer Service  —  Advanced risk analytics and trend detection
---------------------------------------------------------------------
Provides statistical risk analysis, trend detection, velocity profiling,
and customer behavioural scoring beyond the per-transaction ML model.

Used by the dashboard API and reports API for aggregate analytics.
"""
import logging
from datetime import datetime, timedelta
from collections import defaultdict

from sqlalchemy import func

from app.models.models import db, Transaction, RiskScore, FraudAlert, Customer

logger = logging.getLogger(__name__)


class RiskAnalyzer:
    """
    Stateless analytics engine.
    All methods query the database and return serialisable results.
    Must be called within a Flask application context.
    """

    # ── Velocity Profiling ─────────────────────────────────────────────────────

    @staticmethod
    def customer_velocity(customer_id: int, window_hours: int = 24) -> dict:
        """
        Compute transaction velocity metrics for a single customer
        over a rolling time window.

        Returns counts, total amount, and average interval between transactions.
        """
        since = datetime.utcnow() - timedelta(hours=min(window_hours, 720))

        txs = (
            Transaction.query
            .filter(
                Transaction.customer_id == customer_id,
                Transaction.timestamp >= since,
            )
            .order_by(Transaction.timestamp.asc())
            .all()
        )

        if not txs:
            return {
                'customer_id':     customer_id,
                'window_hours':    window_hours,
                'transaction_count': 0,
                'total_amount':    0.0,
                'avg_amount':      0.0,
                'avg_interval_minutes': None,
                'max_amount':      0.0,
                'fraud_count':     0,
                'velocity_risk':   'low',
            }

        amounts     = [t.amount for t in txs]
        fraud_count = sum(1 for t in txs if t.is_fraud)

        # Average time between consecutive transactions
        intervals = []
        for i in range(1, len(txs)):
            delta = (txs[i].timestamp - txs[i - 1].timestamp).total_seconds() / 60
            intervals.append(delta)
        avg_interval = round(sum(intervals) / len(intervals), 1) if intervals else None

        # Simple velocity risk heuristic
        count = len(txs)
        if count >= 10 or (avg_interval is not None and avg_interval < 5):
            velocity_risk = 'critical'
        elif count >= 5 or (avg_interval is not None and avg_interval < 15):
            velocity_risk = 'high'
        elif count >= 3:
            velocity_risk = 'medium'
        else:
            velocity_risk = 'low'

        return {
            'customer_id':          customer_id,
            'window_hours':         window_hours,
            'transaction_count':    count,
            'total_amount':         round(sum(amounts), 2),
            'avg_amount':           round(sum(amounts) / count, 2),
            'max_amount':           round(max(amounts), 2),
            'avg_interval_minutes': avg_interval,
            'fraud_count':          fraud_count,
            'velocity_risk':        velocity_risk,
        }

    # ── Portfolio Risk Summary ─────────────────────────────────────────────────

    @staticmethod
    def portfolio_risk_summary(days: int = 30) -> dict:
        """
        System-wide risk summary for the last N days.
        Returns distribution, trend direction, and top risk contributors.
        """
        since = datetime.utcnow() - timedelta(days=min(days, 365))

        # Score distribution
        distribution = {
            level: RiskScore.query
            .join(Transaction, RiskScore.transaction_id == Transaction.id)
            .filter(
                Transaction.timestamp >= since,
                RiskScore.risk_level == level,
            ).count()
            for level in ('low', 'medium', 'high', 'critical')
        }
        total_scored = sum(distribution.values())

        # Average scores
        agg = db.session.query(
            func.avg(RiskScore.combined_score).label('avg'),
            func.avg(RiskScore.rule_score).label('avg_rule'),
            func.avg(RiskScore.ml_score).label('avg_ml'),
            func.max(RiskScore.combined_score).label('max_score'),
        ).join(Transaction, RiskScore.transaction_id == Transaction.id).filter(
            Transaction.timestamp >= since
        ).first()

        # Week-over-week trend
        prev_since = since - timedelta(days=days)
        prev_avg = db.session.query(func.avg(RiskScore.combined_score)).join(
            Transaction, RiskScore.transaction_id == Transaction.id
        ).filter(
            Transaction.timestamp >= prev_since,
            Transaction.timestamp < since,
        ).scalar() or 0

        current_avg = float(agg.avg or 0)
        trend = 'stable'
        if current_avg > float(prev_avg) * 1.10:
            trend = 'increasing'
        elif current_avg < float(prev_avg) * 0.90:
            trend = 'decreasing'

        return {
            'period_days':       days,
            'total_scored':      total_scored,
            'distribution':      distribution,
            'distribution_pct':  {
                k: round(v / total_scored * 100, 1) if total_scored else 0
                for k, v in distribution.items()
            },
            'averages': {
                'combined': round(current_avg, 4),
                'rule':     round(float(agg.avg_rule or 0), 4),
                'ml':       round(float(agg.avg_ml   or 0), 4),
                'max':      round(float(agg.max_score or 0), 4),
            },
            'trend':             trend,
            'prev_period_avg':   round(float(prev_avg), 4),
        }

    # ── High Risk Customers ────────────────────────────────────────────────────

    @staticmethod
    def top_risk_customers(limit: int = 10) -> list[dict]:
        """
        Return customers ranked by their average combined risk score
        across all their transactions.
        """
        rows = (
            db.session.query(
                Customer.id,
                Customer.name,
                Customer.customer_id,
                Customer.risk_level,
                Customer.country,
                func.avg(RiskScore.combined_score).label('avg_risk'),
                func.count(Transaction.id).label('tx_count'),
                func.sum(db.cast(Transaction.is_fraud, db.Integer)).label('fraud_count'),
            )
            .join(Transaction, Transaction.customer_id == Customer.id)
            .join(RiskScore, RiskScore.transaction_id == Transaction.id)
            .group_by(Customer.id)
            .order_by(func.avg(RiskScore.combined_score).desc())
            .limit(min(limit, 50))
            .all()
        )

        return [
            {
                'customer_id':   r.customer_id,
                'name':          r.name,
                'risk_level':    r.risk_level,
                'country':       r.country,
                'avg_risk_score': round(float(r.avg_risk), 4),
                'transaction_count': r.tx_count,
                'fraud_count':   int(r.fraud_count or 0),
            }
            for r in rows
        ]

    # ── Fraud Pattern Detection ────────────────────────────────────────────────

    @staticmethod
    def fraud_patterns(days: int = 7) -> dict:
        """
        Detect recurring fraud patterns in recent transactions.
        Groups by: merchant category, location, card type, hour of day.
        """
        since = datetime.utcnow() - timedelta(days=min(days, 90))

        fraudulent = (
            Transaction.query
            .filter(
                Transaction.timestamp >= since,
                Transaction.is_fraud == True,
            )
            .all()
        )

        by_category = defaultdict(int)
        by_location  = defaultdict(int)
        by_card_type = defaultdict(int)
        by_hour      = defaultdict(int)

        for t in fraudulent:
            by_category[t.merchant_category or 'unknown'] += 1
            by_location[t.location or 'unknown']           += 1
            by_card_type[t.card_type or 'unknown']          += 1
            by_hour[t.timestamp.hour]                        += 1

        def _top(d: dict, n: int = 5) -> list[dict]:
            return [
                {'label': k, 'count': v}
                for k, v in sorted(d.items(), key=lambda x: -x[1])[:n]
            ]

        return {
            'period_days':        days,
            'total_fraud':        len(fraudulent),
            'by_merchant_category': _top(by_category),
            'by_location':          _top(by_location),
            'by_card_type':         _top(by_card_type),
            'by_hour_of_day':       _top(by_hour),
            'peak_fraud_hour':      max(by_hour, key=by_hour.get) if by_hour else None,
        }

    # ── Alert Escalation Analysis ──────────────────────────────────────────────

    @staticmethod
    def alert_escalation_stats(days: int = 30) -> dict:
        """
        Analyse alert severity distribution and resolution rates.
        Useful for measuring analyst workload and SLA compliance.
        """
        since = datetime.utcnow() - timedelta(days=min(days, 365))

        severity_levels = ('low', 'medium', 'high', 'critical')
        stats = {}

        for sev in severity_levels:
            total = FraudAlert.query.filter(
                FraudAlert.created_at >= since,
                FraudAlert.severity == sev,
            ).count()

            resolved = FraudAlert.query.filter(
                FraudAlert.created_at >= since,
                FraudAlert.severity == sev,
                FraudAlert.is_resolved == True,
            ).count()

            stats[sev] = {
                'total':       total,
                'resolved':    resolved,
                'open':        total - resolved,
                'resolve_rate': round(resolved / total * 100, 1) if total else 0,
            }

        total_all    = sum(s['total']    for s in stats.values())
        resolved_all = sum(s['resolved'] for s in stats.values())

        return {
            'period_days':    days,
            'by_severity':    stats,
            'overall': {
                'total':        total_all,
                'resolved':     resolved_all,
                'open':         total_all - resolved_all,
                'resolve_rate': round(resolved_all / total_all * 100, 1) if total_all else 0,
            },
        }

    # ── Score Trend (daily averages) ──────────────────────────────────────────

    @staticmethod
    def daily_score_trend(days: int = 14) -> list[dict]:
        """
        Return daily average risk scores for the last N days.
        Used for trend line charts in the analytics dashboard.
        """
        result = []
        for i in range(days - 1, -1, -1):
            day_start = (datetime.utcnow() - timedelta(days=i)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            day_end = day_start + timedelta(days=1)

            agg = db.session.query(
                func.avg(RiskScore.combined_score).label('avg'),
                func.count(RiskScore.id).label('count'),
            ).join(
                Transaction, RiskScore.transaction_id == Transaction.id
            ).filter(
                Transaction.timestamp >= day_start,
                Transaction.timestamp < day_end,
            ).first()

            result.append({
                'date':        day_start.strftime('%Y-%m-%d'),
                'label':       day_start.strftime('%b %d'),
                'avg_score':   round(float(agg.avg or 0), 4),
                'tx_count':    agg.count or 0,
            })

        return result
