import argparse
from dataclasses import dataclass


@dataclass
class AppConfig:
    url: str
    url_contains: str
    attach: bool
    cdp: str
    auto_switch_tabs: bool
    rows: int
    poll_seconds: int
    startup_grace: int
    min_incidents: int
    trend_window_min: int
    spike_window_min: int
    spike_delta: int
    new_alarm_incidents: int
    update_min_delta: int
    update_cooldown_min: int
    heartbeat_minutes: int
    recover_on_gateway: bool
    recover_on_stale: bool
    stale_minutes: int
    gateway_refresh_cooldown_min: int
    stale_refresh_cooldown_min: int
    force_today_date: bool
    fail_alert_after: int
    fail_alert_cooldown_min: int
    recover_sleep_seconds: int
    prune_after_min: int


def parse_args() -> AppConfig:
    ap = argparse.ArgumentParser()

    ap.add_argument("--url", default="https://rmesd-prod1.c4.rme.logistics.a2z.com/data/perspective/client/FC_Alarm/site")
    ap.add_argument("--url-contains", default="/data/perspective/client/FC_Alarm/site")

    ap.add_argument("--attach", action="store_true")
    ap.add_argument("--cdp", default="http://127.0.0.1:9222")
    ap.add_argument(
        "--auto-switch-tabs",
        action="store_true",
        help="kept for compatibility; tab picking already happens in attach mode",
    )

    ap.add_argument("--rows", type=int, default=10)
    ap.add_argument("--poll-seconds", type=int, default=30)
    ap.add_argument("--startup-grace", type=int, default=30)

    ap.add_argument("--min-incidents", type=int, default=1)
    ap.add_argument("--trend-window-min", type=int, default=15)
    ap.add_argument("--spike-window-min", type=int, default=3)
    ap.add_argument("--spike-delta", type=int, default=5)
    ap.add_argument("--new-alarm-incidents", type=int, default=10)

    ap.add_argument("--update-min-delta", type=int, default=2)
    ap.add_argument("--update-cooldown-min", type=int, default=15)

    ap.add_argument("--heartbeat-minutes", type=int, default=30)

    ap.add_argument("--recover-on-gateway", action="store_true", default=True)
    ap.add_argument("--recover-on-stale", action="store_true", default=True)
    ap.add_argument("--stale-minutes", type=int, default=60)
    ap.add_argument("--gateway-refresh-cooldown-min", type=int, default=5)
    ap.add_argument("--stale-refresh-cooldown-min", type=int, default=30)

    ap.add_argument(
        "--force-today-date",
        action="store_true",
        help="Only attempts date selection during recovery (best-effort).",
    )

    ap.add_argument("--fail-alert-after", type=int, default=3)
    ap.add_argument("--fail-alert-cooldown-min", type=int, default=15)
    ap.add_argument("--recover-sleep-seconds", type=int, default=8)

    ap.add_argument("--prune-after-min", type=int, default=240)

    args = ap.parse_args()

    return AppConfig(
        url=args.url,
        url_contains=args.url_contains,
        attach=args.attach,
        cdp=args.cdp,
        auto_switch_tabs=args.auto_switch_tabs,
        rows=args.rows,
        poll_seconds=args.poll_seconds,
        startup_grace=args.startup_grace,
        min_incidents=args.min_incidents,
        trend_window_min=args.trend_window_min,
        spike_window_min=args.spike_window_min,
        spike_delta=args.spike_delta,
        new_alarm_incidents=args.new_alarm_incidents,
        update_min_delta=args.update_min_delta,
        update_cooldown_min=args.update_cooldown_min,
        heartbeat_minutes=args.heartbeat_minutes,
        recover_on_gateway=args.recover_on_gateway,
        recover_on_stale=args.recover_on_stale,
        stale_minutes=args.stale_minutes,
        gateway_refresh_cooldown_min=args.gateway_refresh_cooldown_min,
        stale_refresh_cooldown_min=args.stale_refresh_cooldown_min,
        force_today_date=args.force_today_date,
        fail_alert_after=args.fail_alert_after,
        fail_alert_cooldown_min=args.fail_alert_cooldown_min,
        recover_sleep_seconds=args.recover_sleep_seconds,
        prune_after_min=args.prune_after_min,
    )