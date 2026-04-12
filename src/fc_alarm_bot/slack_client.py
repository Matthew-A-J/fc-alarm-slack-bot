import os
import json
import requests


def slack_send(token: str, channel: str, text: str):
    url = "https://slack.com/api/chat.postMessage"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    data = {"channel": channel, "text": text}
    r = requests.post(url, headers=headers, data=json.dumps(data), timeout=15)
    try:
        j = r.json()
    except Exception:
        j = {"ok": False, "error": f"non-json response {r.status_code}"}
    if not j.get("ok", False):
        raise RuntimeError(f"Slack API error: {j.get('error')}")


def slack_send_to_channel(text: str, *, channel: str, mention: str = ""):
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Missing SLACK_BOT_TOKEN")
    msg = f"{mention}\n{text}".strip() if mention else text
    slack_send(token, channel, msg)