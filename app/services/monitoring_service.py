"""
Real-Time Transaction Monitoring Service
════════════════════════════════════════
Evaluates transactions instantly against configurable risk thresholds,
flags suspicious activity for review or automatic blocking, and maintains
sliding-window streaming analytics for high-volume financial networks.

Architecture
────────────
  ┌──────────────┐   submit    ┌───────────────────┐   score   ┌──────────────┐
  │  Transaction  │──────────►│ MonitoringService  │──────────►│ FraudPipeline│
  │   Payload     │           │  (this module)     │           │  (existing)  │
  └──────────────┘           └───────────────────┘           └──────────────┘
                                       │
                          ┌────────────┼────────────┐
                          ▼            ▼             ▼
                    Threshold      Streaming     Network
                    Engine         Analytics     Analysis
                  (real-time)    (sliding win)  (device/IP)

Streaming Windows
─────────────────
  • 1-minute  — burst detection
  • 5-minute  — velocity spikes
  • 1-hour    — sustained anomalies
  All windows are in-memory thread-safe deques (no Redis required).

Network Analysis
────────────────
  Detects shared device IDs and IP addresses across multiple customers —
  a key indicator of organised fraud rings and account takeover campaigns.

Thread safety
─────────────
  All mutable state protected by threading.Lock().
  Safe for multi-threaded Gunicorn deployments.
"""

import logging
import threading
from collections import deque, defaultdict
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── Default threshold configuration ──────────────────────────────────────────

DEFAULT_THRESHOLDS = {
    # Score-based
    'auto_block_score':       0.75,   # combined_score ≥ this → immediate block
    'auto_flag_score':        0.45,   # combined_score ≥ this → flagged for review
    'critical_alert_score':   0.80,   # generate CRITICAL alert

    # Volume-based (per customer, sliding windows)
    'max_tx_per_minute':      5,      # burst: > 5 tx/min from same customer
    'max_tx_per_5min':        15,     # velocity: > 15 tx/5min from same customer
    'max_tx_per_hour':        50,     # sustained: > 50 tx/hr from same customer

    # Amount-based (per customer)
    'max_amount_per_hour':    100_000, # total spend cap per hour (USD)
    'single_tx_alert':        10_000,  # single transaction worth alerting on

    # Network-based
    'max_customers_per_device': 3,    # > 3 different customers sharing a device → ring
    'max_customers_per_ip':     5,    # > 5 different customers from same IP → ring

    # System-wide rate monitoring
    'system_block_rate_warn':  0.20,  # system-wide block rate > 20% → alert
    'system_tx_rate_warn':     1000,  # > 1000 tx/min system-wide → alert
}


# ─────────────────────────────────────────────────────────────────────────────
# Sliding Window Counter
# ─────────────────────────────────────────────────────────────────────────────

class SlidingWindowCounter:
    """
    Thread-safe sliding window counter backed by a deque of (timestamp, value) tuples.
    Automatically evicts entries older than window_seconds on each operation.
    """

    def __init__(self, window_seconds: int):
        self._window  = timedelta(seconds=window_seconds)
        self._entries = deque()          # (datetime, numeric_value)
        self._lock    = threading.Lock()

    def add(self, value: float = 1.0):
        now = datetime.utcnow()
        with self._lock:
            self._entries.append((now, value))
            self._evict(now)

    def count(self) -> int:
        """Number of events in the current window."""
        now = datetime.utcnow()
        with self._lock:
            self._evict(now)
            return len(self._entries)

    def total(self) -> float:
        """Sum of values in the current window."""
        now = datetime.utcnow()
        with self._lock:
            self._evict(now)
            return sum(v for _, v in self._entries)

    def rate_per_minute(self) -> float:
        """Average events per minute over the window."""
        now = datetime.utcnow()
        with self._lock:
            self._evict(now)
            minutes = self._window.total_seconds() / 60
            return round(len(self._entries) / minutes, 2) if minutes else 0.0

    def _evict(self, now: datetime):
        cutoff = now - self._window
        while self._entries and self._entries[0][0] < cutoff:
            self._entries.popleft()


# ─────────────────────────────────────────────────────────────────────────────
# Threshold Engine
# ─────────────────────────────────────────────────────────────────────────────

class ThresholdEngine:
    """
    Evaluates a transaction + its fraud score against all configured thresholds.
    Returns a list of threshold violations with severity and recommended action.
    """

    def __init__(self, thresholds: dict):
        self._th = thresholds

    def evaluate(self, tx_data: dict, score: float,
                 customer_windows: dict, network_flags: dict) -> list:
        """
        Parameters
        ──────────
        tx_data         : cleaned transaction dict (from ingestion pipeline)
        score           : combined fraud score ∈ [0, 1]
        customer_windows: {window_name: count/total} for this customer
        network_flags   : {device_customers: int, ip_customers: int}

        Returns list of threshold violation dicts.
        """
        violations = []

        # ── Score-based thresholds ────────────────────────────────────────
        if score >= self._th['critical_alert_score']:
            violations.append({
                'threshold':   'CRITICAL_SCORE',
                'value':       round(score, 4),
                'limit':       self._th['critical_alert_score'],
                'severity':    'critical',
                'action':      'block',
                'description': f'Risk score {score:.1%} exceeds critical threshold '
                               f'({self._th["critical_alert_score"]:.1%})',
            })
        elif score >= self._th['auto_block_score']:
            violations.append({
                'threshold':   'AUTO_BLOCK_SCORE',
                'value':       round(score, 4),
                'limit':       self._th['auto_block_score'],
                'severity':    'high',
                'action':      'block',
                'description': f'Risk score {score:.1%} triggers automatic block',
            })
        elif score >= self._th['auto_flag_score']:
            violations.append({
                'threshold':   'AUTO_FLAG_SCORE',
                'value':       round(score, 4),
                'limit':       self._th['auto_flag_score'],
                'severity':    'medium',
                'action':      'flag',
                'description': f'Risk score {score:.1%} flagged for analyst review',
            })

        # ── Single-transaction amount ─────────────────────────────────────
        amount = tx_data.get('amount', 0)
        if amount >= self._th['single_tx_alert']:
            violations.append({
                'threshold':   'HIGH_VALUE_TX',
                'value':       amount,
                'limit':       self._th['single_tx_alert'],
                'severity':    'medium',
                'action':      'flag',
                'description': f'Transaction ${amount:,.2f} exceeds single-TX alert '
                               f'threshold (${self._th["single_tx_alert"]:,.0f})',
            })

        # ── Customer velocity windows ─────────────────────────────────────
        c1m  = customer_windows.get('count_1min', 0)
        c5m  = customer_windows.get('count_5min', 0)
        c1h  = customer_windows.get('count_1hr',  0)
        a1h  = customer_windows.get('amount_1hr', 0.0)

        if c1m > self._th['max_tx_per_minute']:
            violations.append({
                'threshold':   'BURST_RATE_1MIN',
                'value':       c1m,
                'limit':       self._th['max_tx_per_minute'],
                'severity':    'high',
                'action':      'flag',
                'description': f'{c1m} transactions in 1 minute '
                               f'(limit: {self._th["max_tx_per_minute"]})',
            })

        if c5m > self._th['max_tx_per_5min']:
            violations.append({
                'threshold':   'VELOCITY_5MIN',
                'value':       c5m,
                'limit':       self._th['max_tx_per_5min'],
                'severity':    'high',
                'action':      'flag',
                'description': f'{c5m} transactions in 5 minutes '
                               f'(limit: {self._th["max_tx_per_5min"]})',
            })

        if c1h > self._th['max_tx_per_hour']:
            violations.append({
                'threshold':   'VELOCITY_1HOUR',
                'value':       c1h,
                'limit':       self._th['max_tx_per_hour'],
                'severity':    'critical',
                'action':      'block',
                'description': f'{c1h} transactions in 1 hour '
                               f'(limit: {self._th["max_tx_per_hour"]})',
            })

        if a1h > self._th['max_amount_per_hour']:
            violations.append({
                'threshold':   'AMOUNT_VELOCITY_1HR',
                'value':       round(a1h, 2),
                'limit':       self._th['max_amount_per_hour'],
                'severity':    'critical',
                'action':      'block',
                'description': f'Total spend ${a1h:,.2f} in 1 hour exceeds '
                               f'limit (${self._th["max_amount_per_hour"]:,.0f})',
            })

        # ── Network-based thresholds ──────────────────────────────────────
        dev_customers = network_flags.get('device_customers', 0)
        ip_customers  = network_flags.get('ip_customers', 0)

        if dev_customers > self._th['max_customers_per_device']:
            violations.append({
                'threshold':   'DEVICE_SHARING',
                'value':       dev_customers,
                'limit':       self._th['max_customers_per_device'],
                'severity':    'critical',
                'action':      'flag',
                'description': f'Device shared by {dev_customers} different customers '
                               f'— possible fraud ring (limit: '
                               f'{self._th["max_customers_per_device"]})',
            })

        if ip_customers > self._th['max_customers_per_ip']:
            violations.append({
                'threshold':   'IP_CLUSTERING',
                'value':       ip_customers,
                'limit':       self._th['max_customers_per_ip'],
                'severity':    'high',
                'action':      'flag',
                'description': f'IP address used by {ip_customers} different customers '
                               f'(limit: {self._th["max_customers_per_ip"]})',
            })

        return violations


# ─────────────────────────────────────────────────────────────────────────────
# Network Analyser
# ─────────────────────────────────────────────────────────────────────────────

class NetworkAnalyser:
    """
    Tracks device → customer and IP → customer relationships in memory.
    Detects fraud rings where multiple customer accounts share infrastructure.

    Data structures (all protected by a single lock):
      _device_to_customers : { device_hash → set of customer_ids }
      _ip_to_customers     : { ip_address  → set of customer_ids }
      _customer_to_devices : { customer_id → set of device hashes }
    """

    def __init__(self):
        self._device_customers  = defaultdict(set)
        self._ip_customers      = defaultdict(set)
        self._customer_devices  = defaultdict(set)
        self._lock              = threading.Lock()

    def record(self, customer_id: str, device_id: Optional[str],
               ip_address: Optional[str]):
        """Register a new data point for network analysis."""
        with self._lock:
            if device_id and device_id not in ('DEV-unknown', 'unknown'):
                self._device_customers[device_id].add(customer_id)
                self._customer_devices[customer_id].add(device_id)
            if ip_address:
                # Anonymise: zero last octet for grouping (privacy-safe)
                import re
                anon_ip = re.sub(r'\.\d+$', '.0', ip_address)
                self._ip_customers[anon_ip].add(customer_id)

    def get_flags(self, customer_id: str, device_id: Optional[str],
                  ip_address: Optional[str]) -> dict:
        """Return network risk flags for this transaction."""
        import re
        with self._lock:
            dev_customers = len(self._device_customers.get(device_id, set())) \
                            if device_id else 0
            anon_ip = re.sub(r'\.\d+$', '.0', ip_address) if ip_address else None
            ip_customers = len(self._ip_customers.get(anon_ip, set())) \
                           if anon_ip else 0
            customer_device_count = len(self._customer_devices.get(customer_id, set()))

        return {
            'device_customers':       dev_customers,
            'ip_customers':           ip_customers,
            'customer_device_count':  customer_device_count,
            'multi_device':           customer_device_count > 3,
        }

    def get_network_summary(self) -> dict:
        """Return a snapshot of the current network graph metrics."""
        with self._lock:
            shared_devices = {d: list(c) for d, c in self._device_customers.items()
                              if len(c) > 1}
            shared_ips     = {ip: list(c) for ip, c in self._ip_customers.items()
                              if len(c) > 1}
        return {
            'shared_devices':        len(shared_devices),
            'shared_ips':            len(shared_ips),
            'top_shared_devices':    sorted(
                [{'device': d[:12] + '…', 'customers': len(c)}
                 for d, c in shared_devices.items()],
                key=lambda x: x['customers'], reverse=True
            )[:5],
            'top_shared_ips':        sorted(
                [{'ip': ip, 'customers': len(c)}
                 for ip, c in shared_ips.items()],
                key=lambda x: x['customers'], reverse=True
            )[:5],
        }


# ─────────────────────────────────────────────────────────────────────────────
# Main Monitoring Service
# ─────────────────────────────────────────────────────────────────────────────

class MonitoringService:
    """
    Real-time transaction monitoring orchestrator.

    Usage (called automatically by the fraud pipeline):
        result = monitoring_service.monitor(tx_data, fraud_analysis)
    """

    def __init__(self):
        self._thresholds  = dict(DEFAULT_THRESHOLDS)
        self._th_engine   = ThresholdEngine(self._thresholds)
        self._network     = NetworkAnalyser()
        self._lock        = threading.Lock()

        # Per-customer sliding windows: customer_id → {window: SlidingWindowCounter}
        self._customer_windows: dict[str, dict] = {}

        # System-wide counters
        self._sys_tx_1min   = SlidingWindowCounter(60)
        self._sys_tx_5min   = SlidingWindowCounter(300)
        self._sys_blocked   = SlidingWindowCounter(3600)
        self._sys_flagged   = SlidingWindowCounter(3600)
        self._sys_approved  = SlidingWindowCounter(3600)
        self._sys_amount    = SlidingWindowCounter(3600)

        # Recent monitoring events (last 200, for the live feed)
        self._events: deque = deque(maxlen=200)

    # ── Main entry point ──────────────────────────────────────────────────────

    def monitor(self, tx_data: dict, fraud_result: dict) -> dict:
        """
        Called after every fraud analysis to update streaming analytics,
        evaluate thresholds, and record network relationships.

        Parameters
        ──────────
        tx_data      : preprocessed transaction dict
        fraud_result : output from FraudDetector.analyze_transaction()

        Returns a monitoring result dict added to the fraud_result payload.
        """
        customer_id = str(tx_data.get('customer_id', 'UNKNOWN'))
        device_id   = tx_data.get('device_id')
        ip_address  = tx_data.get('ip_address')
        amount      = float(tx_data.get('amount', 0))
        status      = fraud_result.get('status', 'unknown')
        scores      = fraud_result.get('risk_score', {})
        combined    = float(scores.get('combined_score', 0))

        # ── 1. Update customer sliding windows ────────────────────────────
        windows = self._get_or_create_windows(customer_id)
        windows['count_1min'].add(1)
        windows['count_5min'].add(1)
        windows['count_1hr'].add(1)
        windows['amount_1hr'].add(amount)

        customer_counts = {
            'count_1min':  windows['count_1min'].count(),
            'count_5min':  windows['count_5min'].count(),
            'count_1hr':   windows['count_1hr'].count(),
            'amount_1hr':  windows['amount_1hr'].total(),
        }

        # ── 2. Update network graph ───────────────────────────────────────
        self._network.record(customer_id, device_id, ip_address)
        network_flags = self._network.get_flags(customer_id, device_id, ip_address)

        # ── 3. Evaluate thresholds ────────────────────────────────────────
        threshold_violations = self._th_engine.evaluate(
            tx_data, combined, customer_counts, network_flags
        )

        # ── 4. Update system-wide counters ────────────────────────────────
        self._sys_tx_1min.add()
        self._sys_tx_5min.add()
        self._sys_amount.add(amount)
        if status == 'blocked':
            self._sys_blocked.add()
        elif status == 'flagged':
            self._sys_flagged.add()
        else:
            self._sys_approved.add()

        # ── 5. Determine monitoring action ────────────────────────────────
        monitoring_action = 'pass'
        if any(v['action'] == 'block' for v in threshold_violations):
            monitoring_action = 'block'
        elif any(v['action'] == 'flag' for v in threshold_violations):
            monitoring_action = 'flag'

        # ── 6. Record event for live feed ─────────────────────────────────
        event = {
            'ts':                  datetime.utcnow().isoformat(),
            'customer_id':         customer_id,
            'amount':              amount,
            'status':              status,
            'combined_score':      round(combined, 4),
            'monitoring_action':   monitoring_action,
            'threshold_hits':      len(threshold_violations),
            'network_flags':       network_flags,
        }
        with self._lock:
            self._events.append(event)

        if threshold_violations:
            logger.warning(
                'MONITOR | customer=%s amount=%.2f score=%.2f '
                'threshold_hits=%d action=%s',
                customer_id, amount, combined,
                len(threshold_violations), monitoring_action
            )

        return {
            'monitoring_action':     monitoring_action,
            'threshold_violations':  threshold_violations,
            'customer_velocity': {
                'tx_last_1min':   customer_counts['count_1min'],
                'tx_last_5min':   customer_counts['count_5min'],
                'tx_last_1hr':    customer_counts['count_1hr'],
                'amount_last_1hr': round(customer_counts['amount_1hr'], 2),
            },
            'network_analysis':      network_flags,
        }

    # ── System-wide streaming stats ───────────────────────────────────────────

    def get_realtime_stats(self) -> dict:
        """
        Return a snapshot of current real-time monitoring metrics.
        Called by GET /api/monitor/realtime (polling) and SSE stream.
        """
        total_1hr = (self._sys_blocked.count() +
                     self._sys_flagged.count() +
                     self._sys_approved.count())
        block_rate = round(self._sys_blocked.count() / total_1hr, 4) if total_1hr else 0.0
        flag_rate  = round(self._sys_flagged.count() / total_1hr, 4) if total_1hr else 0.0

        system_alerts = []
        if block_rate > self._thresholds['system_block_rate_warn']:
            system_alerts.append({
                'type':    'HIGH_BLOCK_RATE',
                'value':   f'{block_rate:.1%}',
                'message': f'System block rate {block_rate:.1%} exceeds '
                           f'{self._thresholds["system_block_rate_warn"]:.0%} threshold',
            })

        tx_rate = self._sys_tx_1min.count()
        if tx_rate > self._thresholds['system_tx_rate_warn']:
            system_alerts.append({
                'type':    'HIGH_TX_RATE',
                'value':   tx_rate,
                'message': f'Transaction rate {tx_rate}/min exceeds '
                           f'{self._thresholds["system_tx_rate_warn"]}/min threshold',
            })

        return {
            'timestamp':    datetime.utcnow().isoformat(),
            'throughput': {
                'tx_last_1min':  self._sys_tx_1min.count(),
                'tx_last_5min':  self._sys_tx_5min.count(),
                'rate_per_min':  self._sys_tx_1min.rate_per_minute(),
            },
            'outcomes_last_1hr': {
                'total':    total_1hr,
                'blocked':  self._sys_blocked.count(),
                'flagged':  self._sys_flagged.count(),
                'approved': self._sys_approved.count(),
                'block_rate': block_rate,
                'flag_rate':  flag_rate,
            },
            'amount_last_1hr':  round(self._sys_amount.total(), 2),
            'network':          self._network.get_network_summary(),
            'system_alerts':    system_alerts,
            'thresholds':       self._thresholds,
        }

    def get_recent_events(self, limit: int = 50) -> list:
        """Return the most recent monitoring events (for the live feed)."""
        with self._lock:
            events = list(self._events)
        return events[-limit:]

    # ── Threshold management ──────────────────────────────────────────────────

    def update_thresholds(self, updates: dict) -> dict:
        """
        Merge updates into the active threshold configuration.
        Only recognised keys are accepted; unknown keys are silently ignored.
        """
        changed = {}
        with self._lock:
            for key, value in updates.items():
                if key in self._thresholds:
                    try:
                        typed = type(self._thresholds[key])(value)
                        self._thresholds[key] = typed
                        changed[key] = typed
                    except (ValueError, TypeError):
                        pass
            # Rebuild threshold engine with new values
            self._th_engine = ThresholdEngine(self._thresholds)
        logger.info('Thresholds updated: %s', changed)
        return changed

    def get_thresholds(self) -> dict:
        with self._lock:
            return dict(self._thresholds)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _get_or_create_windows(self, customer_id: str) -> dict:
        with self._lock:
            if customer_id not in self._customer_windows:
                self._customer_windows[customer_id] = {
                    'count_1min':  SlidingWindowCounter(60),
                    'count_5min':  SlidingWindowCounter(300),
                    'count_1hr':   SlidingWindowCounter(3600),
                    'amount_1hr':  SlidingWindowCounter(3600),
                }
        return self._customer_windows[customer_id]


# ── Singleton ─────────────────────────────────────────────────────────────────
monitoring_service = MonitoringService()
