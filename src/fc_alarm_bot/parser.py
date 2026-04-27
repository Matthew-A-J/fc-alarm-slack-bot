import time
from datetime import datetime

from src.fc_alarm_bot.utils import normalize_text, safe_int, dedupe_key_for


def wait_for_alarm_list(page, timeout_ms=180_000):
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        try:
            if page.locator("[data-row-index]").count() > 0:
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise TimeoutError("Timed out waiting for alarm list/table to appear")


def read_top_rows(page, max_rows: int) -> list[dict]:
    try:
        row_locs = page.locator("[data-row-index]").filter(has=page.locator("[data-column-id= 'Source'],[data-colum-id= 'source']"))
        n = min(row_locs.count(), max_rows)
        out = []
        for i in range(n):
            row = row_locs.nth(i)

            def cell_text(col_id: str) -> str:
                loc = row.locator(f"[data-column-id='{col_id}']")
                if loc.count() == 0:
                    return ""
                return normalize_text(loc.first.inner_text())

            src = cell_text("Source") or cell_text("source")
            area = cell_text("Area") or cell_text("area")
            msg = cell_text("Message") or cell_text("message")
            inc_txt = cell_text("Incidents") or cell_text("incidents")
            dh_txt = cell_text("Downtime Hours") or cell_text("downtime_hours") or cell_text("DowntimeHours")

            incidents = safe_int(inc_txt, 0)

            out.append(
                {
                    "source": src,
                    "area": area,
                    "message": msg,
                    "incidents": incidents,
                    "downtime_hours": dh_txt,
                }
            )
        clean = [] 
        seen = set()

        for r in out:
            if safe_int(r.get("incidents", 0)) <= 0:
                continue

            K = (
                r.get("source", "").strip(),
                r.get("area", "").strip(),
                r.get("message", "").strip(),
                safe_int(r.get("incidents", 0)),
            )

            if K in seen:
                continue

            seen.add(K)
            clean.append(r)

        return clean[:max_rows]
    
    except Exception:
        return []


def gateway_banner_visible(page) -> bool:
    try:
        b = page.locator("div.connection-lost-banner.banner-active")
        if b.count() > 0 and b.first.is_visible():
            return True
    except Exception:
        pass
    try:
        t = page.get_by_text("No Connection to Gateway", exact=False)
        if t.count() > 0 and t.first.is_visible():
            return True
    except Exception:
        pass
    return False


def pick_best_dashboard_page(context, url_contains: str, url_to_open: str, log):
    candidates = []
    for p in context.pages:
        try:
            if url_contains in (p.url or ""):
                candidates.append(p)
        except Exception:
            pass

    if not candidates:
        log("No existing dashboard tab found; opening a new tab...")
        page = context.new_page()
        page.goto(url_to_open, wait_until="domcontentloaded", timeout=120000)
        return page

    def has_rows(p) -> bool:
        try:
            return p.locator("[data-row-index]").count() > 0
        except Exception:
            return False

    def has_refresh(p) -> bool:
        try:
            return p.locator("text=Auto Refresh").first.is_visible() or p.locator("text=Refreshing Data").first.is_visible()
        except Exception:
            return False

    scored = []
    for p in candidates:
        try:
            p.bring_to_front()
        except Exception:
            pass
        score = (10 if has_rows(p) else 0) + (2 if has_refresh(p) else 0)
        scored.append((score, p))

    scored.sort(key=lambda x: x[0], reverse=True)
    page = scored[0][1]
    try:
        page.bring_to_front()
    except Exception:
        pass
    log(f"Selected dashboard tab: url={page.url}")
    return page


def try_set_date_to_today(page) -> tuple[bool, str]:
    now = datetime.now()
    m, d = now.month, now.day
    candidates = [
        f"{m}/{d}",
        f"{m}/{d:02d}",
        f"{m:02d}/{d:02d}",
        now.strftime("%m/%d/%Y"),
        now.strftime("%m/%d/%y"),
    ]

    try:
        btn = page.locator("button:has-text('Today')")
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click(timeout=2000)
            time.sleep(0.3)
    except Exception:
        pass

    for sel in [
        "button:has-text('Date')",
        "button:has-text('Day')",
        "div[role='button']:has-text('Date')",
        "div[role='button']:has-text('Day')",
        "div[role='button']:has-text('Today')",
    ]:
        try:
            loc = page.locator(sel)
            if loc.count() > 0 and loc.first.is_visible():
                loc.first.click(timeout=1500)
                time.sleep(0.3)
                break
        except Exception:
            continue

    for cand in candidates:
        try:
            item = page.get_by_text(cand, exact=False)
            if item.count() > 0 and item.first.is_visible():
                item.first.click(timeout=1500)
                return True, f"Date set to {cand}"
        except Exception:
            continue

    return False, "Date unchanged (selector not found)"