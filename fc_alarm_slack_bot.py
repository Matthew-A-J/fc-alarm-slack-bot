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
def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


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

    HERE = "<!here>"

    # MAIN alerts get @here
    mention_main = HERE

    # HEALTH only uses @here for first failure episode
    mention_health_issue = HERE

    # State
    history = {}
    last_sent_update = {}
    last_sent_trend_level = {}
    last_sent_spike_delta = {}
    last_seen_ts = {}

    last_sig = None
    last_change_ts = time.time()

    # Anti-spam for issues
    consecutive_failures = 0
    here_sent_for_failure_episode = False
    last_fail_alert_ts = 0.0

    # Recovery anti-spam
    last_recovery_ts = 0.0
    recovery_active = False

    last_heartbeat = time.time()

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
                    if last_sig is None:
                        last_sig = sig
                        last_change_ts = time.time()
                    else:
                        if sig != last_sig:
                            last_sig = sig
                            last_change_ts = time.time()

                stale_minutes = int((time.time() - last_change_ts) / 60)

                # Decide if we should attempt recovery (ONLY under conditions)
                should_recover = False
                reason = None

                if gw_visible and args.recover_on_gateway:
                    # gateway-based recovery uses its own cooldown
                    if (time.time() - last_recovery_ts) >= (args.gateway_refresh_cooldown_min * 60):
                        should_recover = True
                        reason = "gateway_visible"

                if (not should_recover) and args.recover_on_stale and stale_minutes >= args.stale_minutes:
                    if (time.time() - last_recovery_ts) >= (args.stale_refresh_cooldown_min * 60):
                        should_recover = True
                        reason = f"stale_{stale_minutes}m"

                # If we can’t read rows but the dashboard exists, treat it as a failure (not “stale change”)
                if len(rows) == 0:
                    consecutive_failures += 1
                    log(f"[WARN] Parsed 0 rows. failures={consecutive_failures} gw_visible={gw_visible} stale={stale_minutes}m")

                    # only alert health after N consecutive failures and cooldown
                    now_ts = time.time()
                    if consecutive_failures >= args.fail_alert_after and (now_ts - last_fail_alert_ts) >= (args.fail_alert_cooldown_min * 60):
                        last_fail_alert_ts = now_ts
                        mention = mention_health_issue if not here_sent_for_failure_episode else ""
                        here_sent_for_failure_episode = True
                        slack_send_to_channel(
                            f"⚠️ Bot can't read the table (0 rows) repeatedly (x{consecutive_failures}).",
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
                    consecutive_failures = 0
                    here_sent_for_failure_episode = False

                # ---- Recovery block (minimal messaging, no spam) ----
                if should_recover:
                    if not recovery_active:
                        recovery_active = True
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

                    last_recovery_ts = time.time()
                    recovery_active = False

                    if ok:
                        slack_send_to_channel(f"✅ Recovery complete. {note}", channel=channel_health, mention="")
                        # After a successful recovery, reset stale timer
                        last_change_ts = time.time()
                        last_sig = None
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
                window_sec = args.trend_window_min * 60

                new_hot, spikes, trends, updates = [], [], [], []
                spike_keys, trend_keys = set(), set()

                for r in rows:
                    k = dedupe_key_for(r)
                    inc = safe_int(r["incidents"])
                    last_seen_ts[k] = now

                    if k not in history:
                        history[k] = deque(maxlen=500)
                        # NEW HOT: first seen at >= threshold
                        if inc >= args.new_alarm_incidents and inc >= args.min_incidents:
                            rr = dict(r)
                            rr["prev_incidents"] = None
                            rr["delta"] = inc
                            rr["window_min"] = args.trend_window_min
                            new_hot.append(rr)

                    history[k].append(SeriesPoint(now, inc))

                    while history[k] and (now - history[k][0].t) > window_sec:
                        history[k].popleft()

                    # SPIKE: Δ over window
                    if len(history[k]) >= 2:
                        oldest = history[k][0].incidents
                        newest = history[k][-1].incidents
                        delta = newest - oldest

                        if newest >= args.min_incidents and delta >= args.spike_delta:
                            prev_best = last_sent_spike_delta.get(k, -10**9)
                            if delta > prev_best:
                                rr = dict(r)
                                rr["prev_incidents"] = oldest
                                rr["delta"] = delta
                                rr["window_min"] = args.trend_window_min
                                spikes.append(rr)
                                last_sent_spike_delta[k] = delta
                                spike_keys.add(k)

                        # TREND: climbing (no @here)
                        prev = history[k][-2].incidents
                        if (k not in spike_keys) and newest >= args.min_incidents and newest > prev:
                            prev_level = last_sent_trend_level.get(k, -10**9)
                            if newest > prev_level:
                                rr = dict(r)
                                rr["prev_incidents"] = oldest
                                rr["delta"] = delta
                                rr["window_min"] = args.trend_window_min
                                trends.append(rr)
                                last_sent_trend_level[k] = newest
                                trend_keys.add(k)

                    # UPDATE: suppress if spike/trend
                    prev_info = last_sent_update.get(k)
                    if prev_info is None:
                        last_sent_update[k] = (inc, 0.0)
                    else:
                        prev_inc, prev_ts = prev_info
                        dnow = inc - int(prev_inc)
                        if abs(dnow) >= args.update_min_delta and (now - prev_ts) >= (args.update_cooldown_min * 60):
                            if (k not in spike_keys) and (k not in trend_keys):
                                rr = dict(r)
                                rr["prev_incidents"] = int(prev_inc)
                                rr["delta"] = dnow
                                rr["window_min"] = None
                                updates.append(rr)
                                last_sent_update[k] = (inc, now)
                            else:
                                # still keep the latest inc, but keep cooldown timestamp
                                last_sent_update[k] = (inc, prev_ts)

                # Dedupe keep-highest incidents per key
                def keep_highest(lst):
                    m = {}
                    for x in lst:
                        kk = dedupe_key_for(x)
                        if kk not in m or safe_int(x["incidents"]) > safe_int(m[kk]["incidents"]):
                            m[kk] = x
                    return list(m.values())

                new_hot = keep_highest(new_hot)
                spikes = keep_highest(spikes)
                trends = keep_highest(trends)
                updates = keep_highest(updates)

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
                if args.heartbeat_minutes > 0 and (time.time() - last_heartbeat) >= (args.heartbeat_minutes * 60):
                    last_heartbeat = time.time()
                    slack_send_to_channel(
                        f"💗 Heartbeat: running | rows={args.rows} | last_change={stale_minutes}m ago",
                        channel=channel_health,
                        mention="",
                    )

                # Prune memory
                if args.prune_after_min > 0:
                    cutoff = now - (args.prune_after_min * 60)
                    dead = [k for k, ts in last_seen_ts.items() if ts < cutoff]
                    for k in dead:
                        history.pop(k, None)
                        last_sent_update.pop(k, None)
                        last_sent_trend_level.pop(k, None)
                        last_sent_spike_delta.pop(k, None)
                        last_seen_ts.pop(k, None)

                log(f"Read {len(rows)} rows. events={len(new_hot)+len(spikes)+len(trends)+len(updates)} stale={stale_minutes}m gw={gw_visible}")
                time.sleep(args.poll_seconds)

            except KeyboardInterrupt:
                slack_send_to_channel("🛑 Bot stopped (Ctrl+C).", channel=channel_health, mention=mention_health_issue)
                raise
            except Exception as e:
                consecutive_failures += 1
                log(f"[WARN] Poll failed (#{consecutive_failures}): {str(e)}")

                now_ts = time.time()
                if consecutive_failures >= args.fail_alert_after and (now_ts - last_fail_alert_ts) >= (args.fail_alert_cooldown_min * 60):
                    last_fail_alert_ts = now_ts
                    mention = mention_health_issue if not here_sent_for_failure_episode else ""
                    here_sent_for_failure_episode = True
                    slack_send_to_channel(
                        f"⚠️ Bot poll failing (x{consecutive_failures}).\n```{str(e)[:240]}```",
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