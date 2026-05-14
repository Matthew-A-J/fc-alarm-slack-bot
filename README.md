# FC Alarm Slack Bot

A Python monitoring bot for an FC alarm dashboard that reads live alarm data, detects events, and sends structured Slack notifications.

## Current Architecture

- `fc_alarm_slack_bot.py` — main runtime/orchestration
- `src/fc_alarm_bot/config.py` — CLI config parsing
- `src/fc_alarm_bot/slack_client.py` — Slack messaging
- `src/fc_alarm_bot/detector.py` — alarm event detection logic
- `src/fc_alarm_bot/state.py` — runtime state management
- `src/fc_alarm_bot/parser.py` — dashboard parsing/browser helpers
- `src/fc_alarm_bot/logger.py` — logging helper
- `src/fc_alarm_bot/utils.py` — shared helpers

## Current Status

Phase 1 refactor complete:
- Modular file structure
- Working bot preserved
- Clean startup/shutdown behavior
- Slack integration extracted
- Config parsing extracted
- Helper and parser logic extracted

## Dashboard Recovery System

The bot continuously validates dashboard state before sending alarm alerts.

It can detect and recover from:

- Wrong dashboard tab
- Incorrect FC Type
- Incorrect Site
- Incorrect Date Range Start
- Login/session interruption
- Partial dashboard loading failures
- Empty or unreadable alarm tables

During recovery:

- Alarm alerts are suppressed to prevent false alerts
- Health-channel notifications are sent to Slack
- The bot attempts to restore the correct dashboard state
- Monitoring resumes only after validation passes

## Features

- Live FC alarm dashboard monitoring
- Slack startup summary and alert notifications
- New-hot alarm detection
- Spike and trend detection
- Dashboard setting validation
- Alert suppression when dashboard data is invalid
- Auto-recovery for wrong Site, FC Type, and Date Range
- Auto-recovery when the wrong dashboard tab is selected
- Login/session recovery for the “Continue to Log In” screen
- Health-channel notifications for failures and recoveries
- Modular Python structure for maintainability

## Planned Improvements

- Smarter calendar month navigation
- Config files for different sites/buildings
- Docker or service-based deployment
- Persistent event history storage
- Slack slash commands for status and top alarms
- Server deployment with auto-restart
- Optional dashboard/API data source if available

## Run

```powershell
python .\fc_alarm_slack_bot.py --rows 10 --poll-seconds 30