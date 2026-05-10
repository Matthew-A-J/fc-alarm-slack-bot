import time
from datetime import datetime, timedelta

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

        # termporary debug 

        scan_limit = min(row_locs.count(), max_rows * 3)
        n = scan_limit
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


def try_set_date_to_today(page) -> bool:
    try:
        print("[DEBUG] Setting date to TODAY")

        today = datetime.now()
        tomorrow = today + timedelta(days=1)

        start_str = f"{today.strftime('%b')} {today.day}, {today.year} 12:00 AM"
        end_str = f"{tomorrow.strftime('%b')} {tomorrow.day}, {tomorrow.year} 12:00 AM"

        inputs = page.locator("input[type='text']")

        for i in range(inputs.count()):
            try:
                print(f"[DEBUG] text input {i} value:", inputs.nth(i).input_value())
            except Exception as e:
                print(f"[DEBUG]text input {i} error:", e)


        start_input = inputs.nth(1)
        end_input = inputs.nth(2)
        start_input.evaluate(
            """(el, value) => {
                el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('chnage', { bubbles: true }));
                el.blur();
            }""",
            start_str,
        )

        time.sleep(0.5)

        end_input.evaluate(
            """(el, value) => {
                el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
                el.blur();
            }""",
            end_str,
        )
        
        time.sleep(0.5)

        page.keyboard.press("Escape")
        page.mouse.click(1000, 300)

        time.sleep(5)

        start_after = inputs.nth(1).input_value()
        end_after = inputs.nth(2).input_value()

        print("[DEBUG] start after:", start_after)
        print("[DEBUG] end after:", end_after)

        if start_str in start_after and end_str in end_after:
            print("[SUCCESS] Date CONFIRMED")

            page.keyboard.press("Enter")
            time.sleep(0.5)

            page.mouse.click(1000, 300)
            time.sleep(2)

            print("[INFO] Dashboard refresh triggered")
            return True
        
        print("[FAIL] Date NOT applied")
        return False

    except Exception as e:
        print(f"[DEBUG] Date set failed: {e}")
        return False


def verify_dashboard_settings(page) -> list[str]:
    problems = []

    el = page.get_by_text("Site View")
    if el.count() == 0 or not el.first.is_visible():
        problems.append("Site View tab not visible")

    el = page.get_by_text("AR SORT")
    if el.count() == 0 or not el.first.is_visible():
        problems.append("AR SORT filter not visible")

    #el = page.get_by_text("OXR1")
    #if el.count() == 0 or not el.first.is_visible():
       # problems.append("OXR1 filter not visible")

    el = page.get_by_text("Jam")
    if el.count() == 0 or not el.first.is_visible():
        problems.append("Jam filter not visible")

    el = page.get_by_text("Top Alarm Events")
    if el.count() == 0 or not el.first.is_visible():
        problems.append("Top Alarm Events filter not visible")
    
    #today = datetime.now()
    #tomorrow = today + timedelta(days=1)

    #today_text = f"{today.strftime('%b')} {today.day}, {today.year}"
    #tomorrow_text = f"{tomorrow.strftime('%b')} {tomorrow.day}, {tomorrow.year}"

    #el = page.get_by_text(today_text)
    #if el.count() == 0 or not el.first.is_visible():
    #    problems.append(f"Date Range Start not set to today ({today_text})")

    #el = page.get_by_text(tomorrow_text)
    #if el.count() == 0 or not el.first.is_visible():
    #    problems.append(f"Date Range End not set to tomorrow ({tomorrow_text})")

    return problems

def try_fix_filters(page):
    try:
        el = page.get_by_text("Site View")
        if el.count() > 0:
            el.first.click()
            time.sleep(0.5)
    except Exception:
        pass

    try:
        el = page.get_by_text("AR SORT")
        if el.count() > 0:
            el.first.click()
            time.sleep(0.5)
    except Exception:
        pass

    try:
        el = page.get_by_text("OXR1")
        if el.count() > 0:
            el.first.click()
            time.sleep(0.5)
    except Exception:
        pass

    try:
        el = page.get_by_text("Jam")
        if el.count() > 0:
            el.first.click()
            time.sleep(0.5)
    except Exception:
        pass

def click_continue_login_if_visible(page):
    try:
        btn = page.get_by_text("CONTINUE TO LOG IN")
        if btn.count() > 0 and btn.first.is_visible():
            btn.first.click(timeout=2000)
            time.sleep(2)
            return True
    
    except Exception:
        pass
    
    return False

def try_set_site(page, site: str = "OXR1") -> bool:
    try:
        print("[DEBUG] Trying Site")

        dropdown = page.locator("div.ia_dropdown").nth(2)
        print("[DEBUG] Site dropdown count:", page.locator("div.ia_dropdown").count())

        if dropdown.count() > 0:
            dropdown.first.click()
            time.sleep(0.5)
            
        page.keyboard.press("Control+A")
        page.keyboard.type(site)
        time.sleep(0.5)
        page.keyboard.press("ArrowDown")
        time.sleep(0.2)
        page.keyboard.press("Enter")
        time.sleep(2)
       
        body = page.locator("body").inner_text()

        if f"Site: {site}" in body:
            print("[SUCESS] Site CONFIRMED")
            return True
        
        else:
            print("[FAIL] Site NOT applied")
    
    except Exception as e:
        print(f"[DEBUG] Site fix failed: {e}")
    
    return False

def click_site_view_if_visible(page) -> bool:
    try:
        tab = page.get_by_text("Site View", exact=True)
        if tab.count() > 0 and tab.first.is_visible():
            tab.first.click(timeout=2000)
            time.sleep(1)
            return True
    except Exception:
        pass
    return False

def try_set_fc_type(page, fc_type: str = "AR SORT") -> bool:
    try:
        print("[DEBUG] Trying FC Type")

        dropdown = page.locator("div.ia_dropdown").nth(1)
        print("[DEBUG] FC dropdown count:", page.locator("div.ia_dropdown").count())

        if dropdown.count() > 0:
            dropdown.first.click()
            time.sleep(0.5)
            
        page.keyboard.press("Control+A")
        page.keyboard.type(fc_type)
        time.sleep(0.5)
        page.keyboard.press("ArrowDown")
        time.sleep(0.2)
        page.keyboard.press("Enter")
        time.sleep(2)
        
        body = page.locator("body").inner_text()

        if "FC Type: AR SORT" in body:
            print("[SUCCESS] FC Type CONFIRMED")
            return True
        else:
            print("[FAIL] FC Type NOT applied")
    
    except Exception as e:
        print(f"[DEBUG] FC Type fix failed: {e}")
    
    
    return False