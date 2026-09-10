"""
integration.py
---------------
Bridges the Tkinter GUI (estate_search_gui.py) to the Playwright scraper for
the Maryland Register of Wills estate search
(https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx).

Only "Input File" mode is wired up for now, as requested. "Main Data" mode
raises a clear error so the GUI can report it rather than silently doing the
wrong thing.

This file also fixes the dropdown-selection bug from the original script:
selecting "Estate Status" (and, on this site, several of the other filter
dropdowns) triggers a server-side postback. If the next field is filled in
before that postback finishes, the selection you just made either never
truly registers or gets wiped out the moment the postback completes — which
is exactly the "I click Estate Type but it won't select" symptom. The fix
is `select_dropdown()` below: it selects the option, gives the page a beat
to finish any postback, then RE-FINDS the element (because a postback can
replace the DOM node even though the id stays the same) and verifies the
selection stuck — reapplying it once more if it didn't.
"""

import os
import time
import random
import itertools
from datetime import datetime
# from dotenv import load_dotenv
import pandas as pd
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from commons import get_proxy_settings

# OUTPUT_DIR = "Output"
TEMP_DIR = "Temp"
SEARCH_URL = "https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx"
INPUT_DIR = "Input"

os.makedirs(INPUT_DIR, exist_ok=True)
# load_dotenv()
# ---------------------------------------------------------------------------
# Proxy helper
# ---------------------------------------------------------------------------
# def get_ev():
#     """Return a proxy URL from the PROXY_URL environment variable, or an
#     empty string if none is configured."""
#     return os.environ.get("PROXY_URL", "").strip()

# ---------------------------------------------------------------------------
# Driver setup
# ---------------------------------------------------------------------------
def create_browser(headless=False, playwright_instance=None):
    """Create a Playwright browser instance with optional proxy support."""
    # proxy_url = get_ev()
    # print("Proxy : ",proxy_url)
    # proxy_settings = None
    
    # if proxy_url:
    #     server = proxy_url.split("@")[-1].rstrip("/")
    #     user_name = proxy_url.split("@")[0].split("//")[-1].split(":")[0]
    #     password = proxy_url.split("@")[0].split("//")[-1].split(":")[-1]
    #     proxy_settings = {
    #                 "server": server,
    #                 "username": user_name,
    #                 "password": password
    #             }
    proxy_settings = get_proxy_settings()

    browser = playwright_instance.chromium.launch(
        headless=headless,
        proxy=proxy_settings,
        args=["--no-sandbox", "--disable-dev-shm-usage"]
    )
    context = browser.new_context(
        viewport={"width": 1600, "height": 1000} if headless else None
    )
    page = context.new_page()
    return browser, context, page


# ---------------------------------------------------------------------------
# Robust field helpers — these are the fix for the "can't select estate
# type" bug and similar issues on the other dropdowns.
# ---------------------------------------------------------------------------
def _apply_select(page, element, value):
    """Try to select `value` by option value first, falling back to a
    case-insensitive match on value/text if the exact value isn't found."""
    try:
        page.select_option(element, value=value)
        return
    except Exception:
        pass
    
    target = str(value).strip().upper()
    options = page.query_selector_all(f"{element} option")
    for opt in options:
        opt_value = (opt.get_attribute("value") or "").strip().upper()
        opt_text = (opt.text_content() or "").strip().upper()
        if target in (opt_value, opt_text):
            page.select_option(element, label=opt.text_content())
            return
    
    raise ValueError(f"Option '{value}' not present in dropdown")


def select_dropdown(page, element_id, value, settle_time=1.5, retries=3):
    """Select `value` in the <select id="elem_id"> element, tolerating the
    postback race condition that caused the original script's selections
    (most visibly Estate Type) to silently fail or get reverted.

    Strategy: select -> wait for the page to settle -> RE-FIND the element
    (it may have been replaced by a postback even though the id is the
    same) -> verify the selected value actually stuck -> if not, reapply
    once on the fresh element.
    """
    if not value:
        return  # blank/"any" — nothing to select
    
    selector = f"#{element_id}"
    last_error = None
    
    for attempt in range(1, retries + 1):
        try:
            # Wait for element to be present and enabled
            page.wait_for_selector(selector, state="attached", timeout=5000)
            page.wait_for_selector(f"{selector}:not([disabled])", timeout=5000)
            
            _apply_select(page, selector, value)
            
            # Give any auto-postback triggered by this field time to fire
            page.wait_for_load_state("networkidle", timeout=5000)
            time.sleep(settle_time)
            
            # Verify the selection actually held
            current_value = page.input_value(selector)
            if current_value and current_value.strip().upper() == str(value).strip().upper():
                return  # success
            
            # Didn't stick — reapply once on the fresh element before retrying
            _apply_select(page, selector, value)
            time.sleep(settle_time)
            
            current_value = page.input_value(selector)
            if current_value and current_value.strip().upper() == str(value).strip().upper():
                return
                
        except Exception as exc:
            last_error = exc
            time.sleep(1)
            continue
    
    raise RuntimeError(
        f"Could not select '{value}' in dropdown #{element_id} after {retries} attempts"
        + (f" (last error: {last_error})" if last_error else "")
    )


def find_optional_field(page, id_candidates, css_contains=None):
    """Look for a field by trying several exact ids, then falling back to a
    CSS 'id contains' search. Returns the selector string or None if not found."""
    for cid in id_candidates:
        selector = f"#{cid}"
        try:
            if page.query_selector(selector):
                return selector
        except Exception:
            continue
    
    if css_contains:
        selector = f"[id*='{css_contains}']"
        try:
            if page.query_selector(selector):
                return selector
        except Exception:
            pass
    
    return None


def fill_text_field(page, id_candidates, value, css_contains=None, field_label=""):
    if not value:
        return
    selector = find_optional_field(page, id_candidates, css_contains)
    if selector is None:
        print(f"[warn] Could not locate field for '{field_label}' — skipping it.")
        return
    try:
        page.fill(selector, "")
        page.fill(selector, value)
        time.sleep(0.5)
    except Exception as exc:
        print(f"[warn] Could not fill '{field_label}': {exc}")


def select_optional_dropdown(page, id_candidates, value, css_contains=None, field_label=""):
    if not value:
        return
    selector = find_optional_field(page, id_candidates, css_contains)
    if selector is None:
        print(f"[warn] Could not locate dropdown for '{field_label}' — skipping it.")
        return
    try:
        # Extract the element ID from the selector
        element_id = selector.lstrip("#")
        select_dropdown(page, element_id, value)
    except Exception as exc:
        print(f"[warn] Could not select '{field_label}' = '{value}': {exc}")


# ---------------------------------------------------------------------------
# Filling out one search + scraping the results grid
# ---------------------------------------------------------------------------
def apply_filters(page, filters):
    """Fill in every field the search form supports from a single filters
    dict (one combination of county/status/type at a time — the site's
    dropdowns are single-select, so multi-selected values from the GUI are
    driven one-at-a-time by run_estate_search)."""
    
    fill_text_field(
        page, ["txtEstateNumber", "txtEstateNo", "txtEstateNbr"],
        filters.get("estate_number"), css_contains="EstateNum",
        field_label="Estate Number",
    )
    fill_text_field(
        page, ["txtLastName"], filters.get("last_name"),
        css_contains="LastName", field_label="Last Name",
    )
    fill_text_field(
        page, ["txtFirstName"], filters.get("first_name"),
        css_contains="FirstName", field_label="First Name",
    )
    
    select_optional_dropdown(
        page, ["cboCounty"], filters.get("county"),
        css_contains="County", field_label="County",
    )
    select_optional_dropdown(
        page, ["cboStatus"], filters.get("estate_status"),
        css_contains="Status", field_label="Estate Status",
    )
    select_optional_dropdown(
        page, ["cboType"], filters.get("estate_type"),
        css_contains="Type", field_label="Estate Type",
    )
    select_optional_dropdown(
        page, ["cboPartyType"], filters.get("party_type"),
        css_contains="PartyType", field_label="Party Type",
    )
    
    date_type = filters.get("filing_date_type", "range")
    if date_type == "exact" and filters.get("filing_date_exact"):
        fill_text_field(
            page, ["DateOfFilingExact", "txtDateOfFilingExact"],
            filters["filing_date_exact"], css_contains="DateOfFilingExact",
            field_label="Exact Filing Date",
        )
    else:
        if filters.get("filing_date_from"):
            fill_text_field(
                page, ["DateOfFilingFrom"], filters["filing_date_from"],
                field_label="Filing Date From",
            )
        if filters.get("filing_date_to"):
            fill_text_field(
                page, ["DateOfFilingTo"], filters["filing_date_to"],
                field_label="Filing Date To",
            )
    
    search_btn = page.wait_for_selector("#cmdSearch", timeout=15000)
    search_btn.click()


def grabbing_links(page):
    """Scrape every page of the results grid. Returns an empty DataFrame
    (rather than raising) if the search produced no results table."""
    try:
        page.wait_for_selector('//table[@id="tblStatus"]//tr/td', timeout=15000)
    except PlaywrightTimeoutError:
        # No results table appeared at all — treat as zero results.
        return pd.DataFrame()
    
    # Get total pages
    total_pge = page.locator('//table[@id="tblStatus"]//tr/td').all_text_contents()
    try:
        total_text = "".join(total_pge)
        final_page = total_text.split("of")[-1].split("(")[0].strip()
        max_page = int(final_page)
    except (ValueError, IndexError):
        max_page = 1
    
    current_page = 1
    res = []
    scraped = 0
    print(f"  Total pages to scrape: {max_page}")
    
    while current_page <= max_page:
        for i in range(5):
            try:
                page.wait_for_selector("#dgSearchResults", timeout=10000)
                rows = page.query_selector_all(
                    '(//table[@id="dgSearchResults"]/tbody/tr[@style="background-color:White;"] | '
                    '//table[@id="dgSearchResults"]/tbody/tr[@style="background-color:#EEEEEE;"])'
                )
                page_items = []
                for row in rows:
                    cells = row.query_selector_all(":scope > td")
                    if len(cells) >= 6:
                        # FIX: no trailing comma — prob_link must be a string,
                        # not a 1-element tuple, or drop_duplicates() will
                        # collapse unrelated rows that happen to share the
                        # same href.
                        href = cells[1].query_selector("a").get_attribute("href") or ""
                        prob_link = (
                            "https://registers.maryland.gov/RowNetWeb/Estates/" + href
                        )
                        items = {
                            "country": cells[0].text_content() or "",
                            "estate": cells[1].query_selector("a").text_content() or "",
                            "filling_date": cells[2].text_content() or "",
                            "date_of_death": cells[3].text_content() or "",
                            "typee": cells[4].text_content() or "",
                            "status": cells[5].text_content() or "",
                            "prob_link": prob_link,
                        }
                        page_items.append(items)
                res.extend(page_items)
                scraped += len(page_items)
                break
            except Exception as e:
                print(f"  [warn] Extraction attempt {i + 1} failed: {e}")
        else:
            print("  [warn] Could not extract this page after 5 attempts — stale grid.")
        
        print(f"  Page {current_page}/{max_page} done, total records so far: {scraped}")
        
        if current_page >= max_page:
            break
        
        old_table = page.query_selector("#dgSearchResults")
        next_num = current_page + 1
        clicked = False
        
        try:
            link = page.query_selector(f"//tr[@class='grid-pager']/td/a[normalize-space()='{next_num}']")
            if link:
                link.click()
                clicked = True
        except Exception:
            pass
        
        if not clicked:
            try:
                dots = page.query_selector_all("//a[contains(text(),'...')]")
                if dots:
                    dots[-1].click()
                    clicked = True
                else:
                    print(f"  [warn] No '...' link and page {next_num} not visible — stopping.")
            except Exception as e:
                print(f"  [warn] Failed to click '...' link: {e}")
        
        if not clicked:
            print(f"  [warn] Could not advance past page {current_page}. Stopping pagination.")
            break
        
        try:
            page.wait_for_selector("#dgSearchResults", timeout=15000)
        except PlaywrightTimeoutError:
            pass
        
        current_page += 1
    
    return pd.DataFrame(res)


# ---------------------------------------------------------------------------
# Public entry point used by the GUI
# ---------------------------------------------------------------------------
def run_estate_search(params):
    mode = params.get("mode")
    if mode != "input_file":
        msg = "Only 'Input File' mode is currently integrated. 'Main Data' mode is coming soon."
        print(f"[error] {msg}")
        return {"success": False, "error": msg}
    
    os.makedirs(TEMP_DIR, exist_ok=True)
    
    county_list = params.get("county") or [""]
    status_list = params.get("estate_status") or [""]
    type_list = params.get("estate_type") or [""]
    combinations = list(itertools.product(county_list, status_list, type_list))
    
    print(f"Running {len(combinations)} search combination(s)...")
    
    headless = params.get("headless", False)
    all_results = []
    
    with sync_playwright() as p:
        browser, context, page = create_browser(headless=headless, playwright_instance=p)
        
        try:
            for idx, (county, status, etype) in enumerate(combinations, start=0):
                print(
                    f"\n[{idx}/{len(combinations)}] County='{county or 'Any'}' "
                    f"Status='{status or 'Any'}' Type='{etype or 'Any'}'"
                )
                page.goto(SEARCH_URL)
                time.sleep(random.uniform(2, 4))
                
                filters = dict(params)
                filters["county"] = county
                filters["estate_status"] = status
                filters["estate_type"] = etype
                
                try:
                    apply_filters(page, filters)
                    time.sleep(random.uniform(2, 4))
                    df = grabbing_links(page)
                    if not df.empty:
                        df["search_county"] = county
                        df["search_status"] = status
                        df["search_type"] = etype
                        all_results.append(df)
                    print(f"  -> {len(df)} record(s) for this combination.")
                except Exception as exc:
                    print(f"  [warn] Combination failed, skipping: {exc}")
                    continue
            
            if all_results:
                final_df = pd.concat(all_results, ignore_index=True)
                # FIX: Only dedup when we actually ran multiple filter
                # combinations, since that's the only case where the same
                # estate can legitimately show up more than once. For a
                # single combination the grid already returns disjoint
                # pages, and prob_link is not guaranteed unique on this
                # site (ASP.NET postback hrefs repeat across rows), so
                # deduping here was silently dropping real records.
                if len(combinations) > 1:
                    key_cols = [c for c in ("estate", "filling_date", "date_of_death", "prob_link")
                                if c in final_df.columns]
                    if key_cols:
                        before = len(final_df)
                        final_df = final_df.drop_duplicates(subset=key_cols)
                        removed = before - len(final_df)
                        if removed:
                            print(f"  Deduped {removed} overlapping record(s) across combinations.")
            else:
                final_df = pd.DataFrame()
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = os.path.join(TEMP_DIR, f"estate_search_results_{timestamp}.csv")
            input_file = os.path.join(INPUT_DIR, "estate_search_results.csv")
            final_df.to_csv(output_file, index=False, encoding="utf-8")
            final_df.to_csv(input_file, index=False, encoding="utf-8")
            
            print(f"\nSaved {len(final_df)} total record(s) to {output_file}")
            return {"success": True, "total_results": len(final_df), "output_file": output_file}
            
        except Exception as exc:
            print(f"[error] Scraping run failed: {exc}")
            return {"success": False, "error": str(exc)}
        
        finally:
            try:
                browser.close()
            except Exception:
                pass


if __name__ == "__main__":
    # Simple manual smoke test — adjust values as needed.
    sample_params = {
        "mode": "input_file",
        "headless": False,
        "debug": True,
        "estate_number": "",
        "county": [],
        "estate_status": ["OPEN"],
        "estate_type": ["FP"],
        "party_type": "Personal Representative",
        "last_name": "",
        "first_name": "",
        "filing_date_type": "range",
        "filing_date_from": "01/01/2025",
        "filing_date_to": "01/31/2025",
        "filing_date_exact": "",
    }
    print(run_estate_search(sample_params))