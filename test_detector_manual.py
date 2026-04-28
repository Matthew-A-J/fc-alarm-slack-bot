from types import SimpleNamespace

from src.fc_alarm_bot.detector import detect_events
from src.fc_alarm_bot.state import BotState

def row(source, area, incidents):
    return { 
        "source": source,
        "area": area,
        "message": "TEST JAM",
        "incidents": incidents,
        "downtime_hours": "",
    }

args = SimpleNamespace(
    trend_window_min=15,
    spike_window_min=3,
    spike_delta=5,
    min_incidents=1,
    new_alarm_incidents=10,
    update_min_delta=2,
    update_cooldown_min=15,
)

state = BotState()

rows = [row("TEST_ALARM", "TEST_AREA", 3)]
print(detect_events(rows, state, args))

rows = [row("TEST_ALARM", "TEST_AREA", 7)]
print(detect_events(rows, state, args))

rows = [row("TEST_ALARM", "TEST_AREA", 8)]
print(detect_events(rows, state, args))