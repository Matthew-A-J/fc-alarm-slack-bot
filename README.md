# FC Alarm Slack Bot

A Python monitoring bot for an FC alarm dashboard that reads live alarm data, detects events, and sends structured Slack notifications.

## Current Architecture

- `fc_alarm_slack_bot.py` — main runtime/orchestration
- `src/fc_alarm_bot/config.py` — CLI config parsing
- `src/fc_alarm_bot/slack_client.py` — Slack messaging
- `src/fc_alarm_bot/utils.py` — shared helpers
- `src/fc_alarm_bot/parser.py` — dashboard parsing/browser helpers

## Current Status

Phase 1 refactor complete:
- Modular file structure
- Working bot preserved
- Clean startup/shutdown behavior
- Slack integration extracted
- Config parsing extracted
- Helper and parser logic extracted

## Run

```powershell
python .\fc_alarm_slack_bot.py --rows 10 --poll-seconds 30