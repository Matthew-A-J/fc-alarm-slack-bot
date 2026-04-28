import time
from collections import deque
from dataclasses import dataclass

from src.fc_alarm_bot.utils import dedupe_key_for, safe_int
from src.fc_alarm_bot.state import BotState

@dataclass
class SeriesPoint:
    t: float
    incidents: int

def detect_events(rows, state: BotState, args):
    now = time.time()
    trend_window_sec = args.trend_window_min * 60
    spike_window_sec = args.spike_window_min * 60

    new_hot, spikes, trends, updates = [], [], [], []
    spike_keys, trend_keys = set(), set()

    for r in rows:
                    k = dedupe_key_for(r)
                    inc = safe_int(r["incidents"])
                    state.last_seen_ts[k] = now

                    if k not in state.history:
                        state.history[k] = deque(maxlen=500)
                        # NEW HOT: first seen at >= threshold
                        if inc >= args.new_alarm_incidents and inc >= args.min_incidents:
                            rr = dict(r)
                            rr["prev_incidents"] = None
                            rr["delta"] = inc
                            rr["window_min"] = args.trend_window_min
                            new_hot.append(rr)

                    state.history[k].append(SeriesPoint(now, inc))

                    while state.history[k] and (now - state.history[k][0].t) > trend_window_sec:
                        state.history[k].popleft()

                    # SPIKE: Δ over window
                    if len(state.history[k]) >= 2:
                        oldest = state.history[k][0].incidents
                        newest = state.history[k][-1].incidents
                        prev   = state.history[k][-2].incidents
                        delta = newest - oldest
                        delta_from_prev = newest - prev
                        spike_cutoff = now - spike_window_sec
                        spike_points = [p for p in state.history[k] if p.t >= spike_cutoff]
                        rapid_delta = 0
                        if spike_points:
                            rapid_delta = newest - spike_points[0].incidents
                            
                        spike_delta = max(delta_from_prev, rapid_delta)

                        
                        if newest >= args.min_incidents and spike_delta >= args.spike_delta:
                            prev_best = state.last_sent_spike_delta.get(k, -10**9)

                            if spike_delta > prev_best:
                                rr = dict(r)
                                rr["prev_incidents"] = oldest
                                rr["delta"] = spike_delta
                                rr["window_min"] = args.trend_window_min
                                spikes.append(rr)
                                state.last_sent_spike_delta[k] = spike_delta
                                spike_keys.add(k)

                        # TREND: climbing (no @here)
                        prev = state.history[k][-2].incidents
                        if (k not in spike_keys) and newest >= args.min_incidents and newest > prev:
                            prev_level = state.last_sent_trend_level.get(k, -10**9)
                            if newest > prev_level:
                                rr = dict(r)
                                rr["prev_incidents"] = oldest
                                rr["delta"] = delta
                                rr["window_min"] = args.trend_window_min
                                trends.append(rr)
                                state.last_sent_trend_level[k] = newest
                                trend_keys.add(k)

                    # UPDATE: suppress if spike/trend
                    prev_info = state.last_sent_update.get(k)
                    if prev_info is None:
                        state.last_sent_update[k] = (inc, 0.0)
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
                                state.last_sent_update[k] = (inc, now)
                            else:
                                # still keep the latest inc, but keep cooldown timestamp
                                state.last_sent_update[k] = (inc, prev_ts)

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
    return new_hot, spikes, trends, updates
