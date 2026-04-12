def safe_int(x, default=0):
    try:
        return int(str(x).strip())
    except Exception:
        return default


def dedupe_key_for(r: dict) -> str:
    src = (r.get("source") or "").strip()
    area = (r.get("area") or "").strip()
    msg = (r.get("message") or "").strip()
    return f"{src}|{area}|{msg}"


def normalize_text(s: str) -> str:
    return " ".join((s or "").split())


def format_rows(header: str, rows: list[dict]) -> str:
    lines = [header.strip(), ""]
    for i, r in enumerate(rows, 1):
        src = r.get("source", "")
        area = r.get("area", "")
        inc = r.get("incidents", "")
        msg = r.get("message", "")
        dh = r.get("downtime_hours", "")

        prev = r.get("prev_incidents")
        delta = r.get("delta")
        win = r.get("window_min")

        if prev is None or delta is None:
            lines.append(f"{i}. *{src}* | Area *{area}* | Incidents *{inc}*")
        else:
            if win is None:
                lines.append(f"{i}. *{src}* | Area *{area}* | Incidents *{prev} → {inc}* ({delta:+d})")
            else:
                lines.append(f"{i}. *{src}* | Area *{area}* | Incidents *{prev} → {inc}* ({delta:+d} in {win}m)")

        if msg:
            lines.append(f"   └ {msg}")
        if dh not in ("", None):
            lines.append(f"   Downtime Hours: {dh}")
        lines.append("")

    return "\n".join(lines).strip()


def signature(rows: list[dict]) -> tuple:
    sig = []
    for r in rows:
        sig.append((dedupe_key_for(r), safe_int(r.get("incidents"))))
    return tuple(sig)