from dataclasses import dataclass, field
from typing import Dict, Any
from collections import deque
import time


@dataclass
class BotState:
    # Alarm tracking
    history: Dict[str, deque] = field(default_factory=dict)
    last_sent_update: Dict[str, tuple] = field(default_factory=dict)
    last_sent_trend_level: Dict[str, int] = field(default_factory=dict)
    last_sent_spike_delta: Dict[str, int] = field(default_factory=dict)
    last_seen_ts: Dict[str, float] = field(default_factory=dict)

    # Change detection
    last_date_fix_ts: float = 0.0
    last_site_fix_ts: float = 0.0
    last_fc_type_fix_ts: float = 0.0
    last_dashboard_issues: set[str] = field(default_factory=set)
    last_sig: Any = None
    last_change_ts: float = field(default_factory=time.time)

    # Failure handling
    consecutive_failures: int = 0
    here_sent_for_failure_episode: bool = False
    last_fail_alert_ts: float = 0.0

    # Recovery
    last_recovery_ts: float = 0.0
    recovery_active: bool = False

    # Heartbeat
    last_heartbeat: float = field(default_factory=time.time)