import os
import time
import json
import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import deque
from src.fc_alarm_bot.config import parse_args
from src.fc_alarm_bot.slack_client import slack_send_to_channel
from src.fc_alarm_bot.utils import (
    dedupe_key_for,
    format_rows,
    normalize_text,
    safe_int,
    signature,
)
from src.fc_alarm_bot.detector import detect_events
from src.fc_alarm_bot.state import BotState
from src.fc_alarm_bot.logger import log
from src.fc_alarm_bot.parser import (
    gateway_banner_visible,
    pick_best_dashboard_page,
    read_top_rows,
    try_set_date_to_today,
    wait_for_alarm_list,
)
import requests
from playwright.sync_api import sync_playwright
import os

# -----------------------------
# Logging
# -----------------------------

# -----------------------------
# Slack
# -----------------------------

# -----------------------------
# Helpers
# -----------------------------

# -----------------------------
# Dashboard detection + parsing
# -----------------------------

# -----------------------------
# Attach mode: pick best tab
# -----------------------------

# -----------------------------
# Best-effort: set date to today (ONLY during recovery)
# -----------------------------

# -----------------------------
# Monitoring logic
# -----------------------------
@dataclass
class SeriesPoint:
    t: float
    incidents: int

def monitor(args):
    # Required env vars
    channel_main = os.getenv("SLACK_CHANNEL_MAIN", "").strip()
    channel_health = os.getenv("SLACK_CHANNEL_HEALTH", "").strip()
    if not channel_main or not channel_health:
        raise RuntimeError("Missing SLACK_CHANNEL_MAIN / SLACK_CHANNEL_HEALTH")
    state = BotState()
    HERE = "<!here>"

    # MAIN alerts get @here
    mention_main = HERE

    # HEALTH only uses @here for first failure episode
    mention_health_issue = HERE


    # Startup message (HEALTH, no @here)
    slack_send_to_channel(
        f"✅ FC Alarm bot started. poll={args.poll_seconds}s | rows={args.rows} | stale={args.stale_minutes}m",
        channel=channel_health,
        mention="",
    )

    with sync_playwright() as p:
        if args.attach:
            browser = p.chromium.connect_over_cdp(args.cdp)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = pick_best_dashboard_page(context, args.url_contains, args.url)
        else:
            browser = p.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.goto(args.url, wait_until="domcontentloaded", timeout=120000)

        log(f"Mode: {'ATTACH' if args.attach else 'LAUNCH'}")
        log("Startup grace (log in if prompted)...")
        time.sleep(args.startup_grace)

        wait_for_alarm_list(page, timeout_ms=180_000)

        while True:
            try:
                rows = read_top_rows(page, args.rows)

                # Track gateway visibility
                gw_visible = gateway_banner_visible(page)

                # Track staleness based on top-rows signature
                if rows:
                    sig = signature(rows)
                    if state.last_sig is None:
                        state.last_sig = sig
                        state.last_change_ts = time.time()
                    else:
                        if sig != state.last_sig:
                            state.last_sig = sig
                            state.last_change_ts = time.time()

                stale_minutes = int((time.time() - state.last_change_ts) / 60)

                # Decide if we should attempt recovery (ONLY under conditions)
                should_recover = False
                reason = None

                if gw_visible and args.recover_on_gateway:
                    # gateway-based recovery uses its own cooldown
                    if (time.time() - state.last_recovery_ts) >= (args.gateway_refresh_cooldown_min * 60):
                        should_recover = True
                        reason = "gateway_visible"

                if (not should_recover) and args.recover_on_stale and stale_minutes >= args.stale_minutes:
                    if (time.time() - state.last_recovery_ts) >= (args.stale_refresh_cooldown_min * 60):
                        should_recover = True
                        reason = f"stale_{stale_minutes}m"

                # If we can’t read rows but the dashboard exists, treat it as a failure (not “stale change”)
                if len(rows) == 0:
                    state.consecutive_failures += 1
                    log(f"[WARN] Parsed 0 rows. failures={state.consecutive_failures} gw_visible={gw_visible} stale={stale_minutes}m")

                    # only alert health after N consecutive failures and cooldown
                    now_ts = time.time()
                    if state.consecutive_failures >= args.fail_alert_after and (now_ts - state.last_fail_alert_ts) >= (args.fail_alert_cooldown_min * 60):
                        state.last_fail_alert_ts = now_ts
                        mention = mention_health_issue if not state.here_sent_for_failure_episode else ""
                        state.here_sent_for_failure_episode = True
                        slack_send_to_channel(
                            f"⚠️ Bot can't read the table (0 rows) repeatedly (x{state.consecutive_failures}).",
                            channel=channel_health,
                            mention=mention,
                        )

                    # Optional: attempt recovery if gateway is visible and cooldown allows
                    if should_recover:
                        # fall through to recovery block below
                        pass
                    else:
                        time.sleep(args.poll_seconds)
                        continue
                else:
                    # success read -> clear failure episode
                    state.consecutive_failures = 0
                    state.here_sent_for_failure_episode = False

                # ---- Recovery block (minimal messaging, no spam) ----
                if should_recover:
                    if not state.recovery_active:
                        state.recovery_active = True
                        slack_send_to_channel(
                            f"🛠️ Recovery starting ({reason}). Reloading dashboard"
                            + (" + set date to today..." if args.force_today_date else "..."),
                            channel=channel_health,
                            mention="",
                        )

                    ok = True
                    note = "Reloaded."
                    try:
                        page.reload(wait_until="domcontentloaded", timeout=120000)
                        wait_for_alarm_list(page, timeout_ms=180_000)
                        if args.force_today_date:
                            changed, dn = try_set_date_to_today(page)
                            note = dn
                    except Exception as e:
                        ok = False
                        note = f"Recovery failed: {str(e)[:200]}"

                    state.last_recovery_ts = time.time()
                    state.recovery_active = False

                    if ok:
                        slack_send_to_channel(f"✅ Recovery complete. {note}", channel=channel_health, mention="")
                        # After a successful recovery, reset stale timer
                        state.last_change_ts = time.time()
                        state.last_sig = None
                    else:
                        # One clean issue alert (no spam loop)
                        slack_send_to_channel(
                            f"⚠️ Recovery attempt failed. {note}",
                            channel=channel_health,
                            mention=mention_health_issue,
                        )

                    time.sleep(args.poll_seconds)
                    continue

                # ---- Alert logic ----
                now = time.time()
                new_hot, spikes, trends, updates = detect_events(rows, state, args)

                # MAIN channel: NEW HOT + SPIKES with @here
                if new_hot:
                    slack_send_to_channel(
                        format_rows(
                            f"🆕🚨 *NEW HOT ALARM* (first-seen ≥ {args.new_alarm_incidents})",
                            new_hot,
                        ),
                        channel=channel_main,
                        mention=mention_main,
                    )

                if spikes:
                    slack_send_to_channel(
                        format_rows(
                            f"🚨 *SPIKE* (Δ ≥ {args.spike_delta} in {args.trend_window_min}m)",
                            spikes,
                        ),
                        channel=channel_main,
                        mention=mention_main,
                    )

                # HEALTH channel: trends/updates/heartbeat (no @here)
                if trends:
                    slack_send_to_channel(
                        format_rows(f"📈 *TRENDING* (climbing within {args.trend_window_min}m)", trends),
                        channel=channel_health,
                        mention="",
                    )

                if updates:
                    slack_send_to_channel(
                        format_rows("🔁 *UPDATE* (changed alarms)", updates),
                        channel=channel_health,
                        mention="",
                    )

                # Heartbeat
                if args.heartbeat_minutes > 0 and (time.time() - state.last_heartbeat) >= (args.heartbeat_minutes * 60):
                    state.last_heartbeat = time.time()
                    slack_send_to_channel(
                        f"💗 Heartbeat: running | rows={args.rows} | last_change={stale_minutes}m ago",
                        channel=channel_health,
                        mention="",
                    )

                # Prune memory
                if args.prune_after_min > 0:
                    cutoff = now - (args.prune_after_min * 60)
                    dead = [k for k, ts in state.last_seen_ts.items() if ts < cutoff]
                    for k in dead:
                        state.history.pop(k, None)
                        state.last_sent_update.pop(k, None)
                        state.last_sent_trend_level.pop(k, None)
                        state.last_sent_spike_delta.pop(k, None)
                        state.last_seen_ts.pop(k, None)

                log(f"Read {len(rows)} rows. events={len(new_hot)+len(spikes)+len(trends)+len(updates)} stale={stale_minutes}m gw={gw_visible}")
                time.sleep(args.poll_seconds)

            except KeyboardInterrupt:
                slack_send_to_channel("🛑 Bot stopped (Ctrl+C).", channel=channel_health, mention=mention_health_issue)
                raise
            except Exception as e:
                import traceback
                traceback.print_exc()
                raise
                now_ts = time.time()
                if state.consecutive_failures >= args.fail_alert_after and (now_ts - state.last_fail_alert_ts) >= (args.fail_alert_cooldown_min * 60):
                    state.last_fail_alert_ts = now_ts
                    mention = mention_health_issue if not state.here_sent_for_failure_episode else ""
                    state.here_sent_for_failure_episode = True
                    slack_send_to_channel(
                        f"⚠️ Bot poll failing (x{state.consecutive_failures}).\n```{str(e)[:240]}```",
                        channel=channel_health,
                        mention=mention,
                    )

                time.sleep(args.recover_sleep_seconds)


def main():
    try:
        args = parse_args()
        monitor(args)
        return 0
    except KeyboardInterrupt:
        print("Bot stopped by user.")
        return 0
    except Exception as e:
        print(f"Fatal error: {e}")
        raise


if __name__ == "__main__":
    raise SystemExit(main())