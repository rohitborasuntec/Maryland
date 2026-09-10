"""
scraper_main_data.py
-------------------
Main data scraper for Maryland Register of Wills - processes estate records
with configurable range limits.

Key behavior (per requirements):
  * The Playwright browser + a SINGLE page are opened once at the start of a
    run and stay open until the very end (no open/close per record). This
    matters most when headless=False, since otherwise a visible browser
    window/tab would appear to flicker open and closed for every record.
  * For every record we ALWAYS try the lightweight "request" method
    (Playwright's page.goto, no extra JS wait) FIRST.
  * We only fall back to the full "Playwright" method (longer render wait)
    when the site tells us we've been rate limited. Plain request errors
    (bad status / exception) are retried via the request method itself,
    and only escalate to Playwright as a last-resort fallback after
    MAX_RETRIES request attempts have failed outright.
  * Every decision point is logged (which method is being attempted, why we
    are/aren't switching, success/failure) so it's obvious from the logs
    which path was taken for each record.
"""

import os
import time
import requests
import random
import asyncio
import pandas as pd
from datetime import datetime
from parsel import Selector
from playwright.async_api import async_playwright
from commons import get_proxy_settings
from search_logger import get_logger, log_event
from modified_script import process_rows

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
OUTPUT_DIR = "Output"
INPUT_DIR = "Input"
SAVE_EVERY = 50          # write to disk after this many new records
PLAYWRIGHT_COOLDOWN = 15 # once rate-limited, stay on playwright this many rows
MAX_RETRIES = 3          # maximum retries for failed requests

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Initialize logger
logger = get_logger()

# ----------------------------------------------------------------------------
# Playwright setup - Global browser instance AND global page (both reused)
# ----------------------------------------------------------------------------
_browser = None
_context = None
_playwright = None
_page = None                # <-- single persistent page, reused for every fetch
_current_headless = False
_is_initialized = False  # Track if browser is initialized


async def initialize_browser(headless=False):
    """Initialize browser + one reusable page. Called ONCE per run.

    The browser, context, and page are all kept open for the entire run
    (start to finish) instead of being recreated per record. This is what
    stops a visible (headless=False) window from appearing to open/close
    repeatedly - we just keep navigating the same page/tab to new URLs.
    """
    global _browser, _context, _playwright, _page, _current_headless, _is_initialized

    # If already initialized and headless mode hasn't changed, just return
    if _is_initialized and _current_headless == headless:
        log_event("Browser already initialized, reusing existing browser/page for the rest of the run", level="debug")
        return _context

    # If headless mode changed, clean up old instance
    if _is_initialized and _current_headless != headless:
        log_event(f"Headless mode changed from {_current_headless} to {headless}, recreating browser", level="info")
        await cleanup_browser()

    # Initialize new browser instance
    log_event(f"Initializing Playwright browser (headless={headless}) - this browser will stay open for the whole run", level="info")
    _playwright = await async_playwright().start()

    # Get proxy settings
    proxy_settings = get_proxy_settings()
    if proxy_settings:
        log_event(f"Using proxy: {proxy_settings.get('server', 'unknown')}", level="info")

    # Launch browser with or without proxy
    browser_kwargs = {
        "headless": headless,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ]
    }

    # Add proxy if configured
    if proxy_settings:
        browser_kwargs["proxy"] = proxy_settings

    _browser = await _playwright.chromium.launch(**browser_kwargs)

    # Create context with viewport and user agent
    context_options = {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    }

    # Add proxy to context if configured
    if proxy_settings:
        context_options["proxy"] = proxy_settings

    _context = await _browser.new_context(**context_options)

    await _context.add_cookies([
        {
            "name": "__cf_bm",
            "value": "0mKvsLm5C8OLSAXwl9HYVHvGuLhh1G.cN6Fw84c9vt8-1771821885-1.0.1.1-13Xb93ANZtk8xsfLpiGCTBadrTUZ1nO4pltZhYRTH.HQq6cbTWGKHAPOUwKdxZULNKsCHuvZBvFNvq__74_Yqrt8O4EqBAz75mn81EEZYh0",
            "domain": ".maryland.gov",
            "path": "/"
        },
        {
            "name": "ASP.NET_SessionId",
            "value": "j01233mbgubtnbps5qclz2i1",
            "domain": ".maryland.gov",
            "path": "/"
        }
    ])

    # Create the ONE page we will reuse for the entire run
    _page = await _context.new_page()
    await _page.set_extra_http_headers({
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "referer": "https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx",
        "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
    })

    _current_headless = headless
    _is_initialized = True
    log_event("Browser + persistent page created successfully (will remain open until cleanup_browser() is called)", level="info")
    return _context


async def cleanup_browser():
    """Clean up browser resources. Only called at the very end of a run
    (or on fatal error), never between records."""
    global _browser, _context, _playwright, _page, _is_initialized

    log_event("Cleaning up browser resources (end of run)", level="info")
    try:
        if _page is not None:
            await _page.close()
            _page = None
        if _context is not None:
            await _context.close()
            _context = None
        if _browser is not None:
            await _browser.close()
            _browser = None
        if _playwright is not None:
            await _playwright.stop()
            _playwright = None
        _is_initialized = False
        log_event("Browser resources cleaned up", level="debug")
    except Exception as e:
        log_event(f"Error during cleanup: {str(e)}", level="warning")


async def get_browser_context(headless=False):
    """Get or create the shared browser context."""
    return await initialize_browser(headless)


def _extract_record_id(url):
    if "&RecordId=" in url:
        return url.split("&RecordId=")[-1]
    elif "RecordId=" in url:
        return url.split("&RecordId=")[-1]
    else:
        return url.split("=")[-1]


async def fetch_via_playwright(url, headless=False):
    """'Full' fetch: navigate the persistent page and wait longer for JS to
    render. Used only when we've detected rate limiting (or as a last-resort
    fallback after repeated hard request failures)."""
    await get_browser_context(headless)  # ensures _page exists, does NOT open a new one
    global _page
    record_id = _extract_record_id(url)

    try:
        log_event(f"[PLAYWRIGHT] Fetching RecordId={record_id} (full render, extra JS wait)", level="info")
        await _page.goto(
            f"https://registers.maryland.gov/RowNetWeb/Estates/frmDocketImages.aspx?src=row&RecordId={record_id}",
            wait_until="domcontentloaded",
            timeout=30000
        )

        # Wait for content to load
        await _page.wait_for_timeout(random.uniform(3000, 8000))

        # Get page content
        content = await _page.content()
        log_event(f"[PLAYWRIGHT] Successfully fetched RecordId={record_id}", level="debug")
        return content

    except Exception as e:
        log_event(f"[PLAYWRIGHT] Error fetching RecordId={record_id}: {str(e)}", level="error")
        raise


# async def fetch_via_requests(url):
#     """'Lightweight' fetch: navigate the SAME persistent page, no extra
#     render wait. This is the method that is ALWAYS tried first for every
#     record."""
#     # await get_browser_context(headless)  # ensures _page exists, does NOT open a new one
#     global _page
#     record_id = _extract_record_id(url)

#     try:
#         log_event(f"[REQUEST] Trying request-based fetch for RecordId={record_id} (tried first, before Playwright)", level="info")
#         response = await _page.goto(
#             f"https://registers.maryland.gov/RowNetWeb/Estates/frmDocketImages.aspx?src=row&RecordId={record_id}",
#             wait_until="domcontentloaded",
#             timeout=30000
#         )
#         content = await _page.content()
#         status = response.status if response is not None else None
#         log_event(f"[REQUEST] Response for RecordId={record_id}: status={status}", level="info")

#         class ResponseWrapper:
#             def __init__(self, status, text_content):
#                 self.status_code = status
#                 self.text = text_content

#         return ResponseWrapper(status, content)

#     except Exception as e:
#         log_event(f"[REQUEST] Failed for RecordId={record_id}: {str(e)}", level="warning")
#         raise


def fetch_via_requests(url):

    record_id = _extract_record_id(url)
    
    cookies = {
        "__cf_bm": "0mKvsLm5C8OLSAXwl9HYVHvGuLhh1G.cN6Fw84c9vt8-1771821885-1.0.1.1-13Xb93ANZtk8xsfLpiGCTBadrTUZ1nO4pltZhYRTH.HQq6cbTWGKHAPOUwKdxZULNKsCHuvZBvFNvq__74_Yqrt8O4EqBAz75mn81EEZYh0",
        "ASP.NET_SessionId": "j01233mbgubtnbps5qclz2i1",
    }
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-US,en;q=0.9",
        "cache-control": "max-age=0",
        "priority": "u=0, i",
        "referer": "https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx",
        "sec-ch-ua": '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "same-origin",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        "Cookie": "ASP.NET_SessionId=ehhqaiv50bvlknsreblu0ind",
    }
    params = {
        "src": "row",
        "RecordId": record_id,
    }

    try:
        log_event(f"[REQUEST] Trying request-based fetch for RecordId={record_id} (tried first, before Playwright)", level="info")
        PROXY = get_proxy_settings(True)
        response = requests.get(
            "https://registers.maryland.gov/RowNetWeb/Estates/frmDocketImages.aspx",
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=30,
            proxies={"http": PROXY, "https": PROXY},
        )
        status = response.status_code if response is not None else None
        log_event(f"[REQUEST] Response for RecordId={record_id}: status={status}", level="info")
        content = response.text
        class ResponseWrapper:
            def __init__(self, status, text_content):
                self.status_code = status
                self.text = text_content

        return ResponseWrapper(status, content)

    except Exception as e:
        log_event(f"[REQUEST] Failed for RecordId={record_id}: {str(e)}", level="warning")
        raise Exception(f"[REQUEST] Failed for RecordId={record_id}: {str(e)}")


def is_rate_limited(sel):
    """Check if the page contains rate limiting message."""
    return bool(
        sel.xpath('//*[contains(text(),"You have exceeded the allowable rate of page requests")]')
        or 
        sel.xpath('//*[contains(text(),"An unexpected error has occured on this website")]')
        
        
    )


# ----------------------------------------------------------------------------
# Field extraction
# ----------------------------------------------------------------------------
def extract_fields(sel, row):
    """Pull every field out of a parsed detail page for one record."""

    def field(label):
        return sel.xpath(
            f'//table[@id="tblEstateData"]//tr/td/span[@class="RowLabel"]'
            f'[contains(text(),"{label}")]//following::td/span[1]/text()'
        ).get()

    estate_number = field("Estate Number:") or row.get("estate", row.get("Estate", ""))

    items = {
        "Country": row.get("country", row.get("Country", "")),
        "Estate": estate_number,
        "Filling Date": row.get("filling_date", ""),
        "date_of_death": row.get("date_of_death", ""),
        "Type": row.get("typee", row.get("Type", "")),
        "Status": field("Status:") or row.get("status", row.get("Status", "")),
        "Estate Number": estate_number,
        "Decedent Name": field("Decedent Name:"),
        "Date of Probate": field("Date of Probate:"),
        "Personal Reps": sel.xpath(
            '//td/span[@id="lblPerReps"][contains(text(),"Personal Reps:")]'
            '/following::span[@id="lblPersonalReps"]//text()'
        ).getall(),
        "Attorney": sel.xpath(
            '//td/span[@id="Label1"][contains(text(),"Attorney:")]'
            '/following::td/span[@id="lblAttorney"]//text()'
        ).getall(),
        "Date Opened": sel.xpath(
            '//td/span[@id="Label14"][contains(text(),"Date Opened:")]'
            '/following::td/span[@id="lblDateOpened"]//text()'
        ).get(),
        "Date of Filing": sel.xpath(
            '//td/span[@id="Label16"][contains(text(),"Date of Filing:")]'
            '/following::td/span[@id="lblDateOfFiling"]//text()'
        ).get(),
        "Date of Will": sel.xpath(
            '//td/span[@id="Label17"][contains(text(),"Date of Will:")]'
            '/following::td/span[@id="lblDateOfWill"]//text()'
        ).get(),
        "link": row.get("prob_link", row.get("link", "")),
    }
    return items


# ----------------------------------------------------------------------------
# Save helpers
# ----------------------------------------------------------------------------
def save_progress(f_res, urls_dfn, file_path=None):
    """Overwrite both output files with current in-memory state."""
    global _data_csv, _status_csv, _start_index, _end_index
    urls_dfn.to_csv(file_path, index=False)

    try:
        if f_res and _data_csv:
            df = pd.DataFrame(f_res)
            df.to_csv(_data_csv, index=False)
            log_event(f"Saved {len(f_res)} records to {_data_csv}", level="debug")

        if _status_csv:
            urls_dfn.to_csv(file_path, index=False)
            log_event(f"Saved status to {_status_csv}", level="debug")
    except Exception as e:
        error_msg = f"Error saving progress: {str(e)}"
        log_event(error_msg, level="error")
        print(error_msg)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        urls_dfn.to_csv(
            os.path.join(OUTPUT_DIR, file_path or f"error_backup_{timestamp}.csv"),
            index=False
        )


# ----------------------------------------------------------------------------
# Main scraper function
# ----------------------------------------------------------------------------
async def run_scraper_async(start, end, input_csv, data_csv, status_csv, headless=False):
    """Asynchronous main scraper function with configurable range.

    Method selection policy (per requirements):
      1. ALWAYS try the request method first for a record, UNLESS we are
         currently inside a "playwright cooldown" window triggered by a
         previous rate-limit hit.
      2. If the request method comes back rate-limited -> re-fetch that
         record via Playwright, and stay on Playwright for the next
         PLAYWRIGHT_COOLDOWN records (the site is clearly throttling us).
      3. If the request method fails for a non-rate-limit reason (bad
         status / exception), retry the REQUEST method itself (up to
         MAX_RETRIES). Only after all request retries are exhausted do we
         fall back to Playwright once, as a last resort, for that record.
    """
    global _start_index, _end_index, _input_csv, _data_csv, _status_csv

    log_event("=" * 60, level="info")
    log_event("MAIN DATA SCRAPER STARTED", level="info")
    log_event(f"Input file: {input_csv}", level="info")
    log_event(f"Output file: {data_csv}", level="info")
    log_event(f"Status file: {status_csv}", level="info")
    log_event(f"Range: {start} to {end}", level="info")
    log_event(f"Headless mode: {headless}", level="info")
    log_event("Method policy: REQUEST first for every record; PLAYWRIGHT only on rate-limit (or as last-resort fallback)", level="info")

    # Set global variables
    _input_csv = input_csv
    _data_csv = data_csv
    _status_csv = status_csv

    # Initialize browser + persistent page ONCE at the start (reused throughout,
    # never closed/reopened per record)
    try:
        await initialize_browser(headless)
        log_event("Browser + page initialized successfully - staying open for the entire run", level="info")
    except Exception as e:
        error_msg = f"Failed to initialize browser: {str(e)}"
        log_event(error_msg, level="error")
        print(f"Error: {error_msg}")
        return []

    # Check if input file exists
    if not os.path.exists(_input_csv):
        error_msg = f"Input file not found: {_input_csv}"
        log_event(error_msg, level="error")
        print(f"Error: {error_msg}")
        await cleanup_browser()
        return []

    try:
        urls_dfn = pd.read_csv(_input_csv)
        log_event(f"Loaded {len(urls_dfn)} URLs from input file", level="info")
    except Exception as e:
        error_msg = f"Failed to read input file: {str(e)}"
        log_event(error_msg, level="error")
        print(f"Error: {error_msg}")
        await cleanup_browser()
        return []

    if "isDone" not in urls_dfn.columns:
        urls_dfn["isDone"] = "Not Done"
        log_event("Added 'isDone' column to status tracking", level="debug")

    f_res = []
    total_urls = len(urls_dfn)

    _start_index = int(start) if start else 0
    _end_index = int(end) if end else total_urls

    # Playwright "cooldown" mode: once we get rate-limited, we stay on
    # Playwright for the next PLAYWRIGHT_COOLDOWN records before trying
    # the request method again.
    use_playwright = False
    playwright_rows_left = 0

    # Ensure we only process the specified range
    start_idx = max(0, _start_index)
    end_idx = min(total_urls, _end_index)

    log_event(f"Actual range: {start_idx} to {end_idx} ({end_idx - start_idx} records)", level="info")

    processed_count = 0
    error_count = 0
    rate_limit_count = 0
    request_failures = 0

    for index, row in urls_dfn.iloc[start_idx:end_idx].iterrows():
        if row["isDone"] == "Done":
            log_event(f"Skipping already processed URL at index {index}", level="debug")
            continue

        url = row["prob_link"] if "prob_link" in row and pd.notna(row.get("prob_link")) else row["link"]
        count = index + 1
        record_id = _extract_record_id(url)
        log_event(f"--- Processing {count}/{total_urls} (RecordId={record_id}) ---", level="info")

        retry_count = 0
        success = False

        while retry_count < MAX_RETRIES and not success:
            try:
                sel = None

                # if use_playwright:
                    # We're in a rate-limit cooldown window - go straight to Playwright
                log_event(f"[MODE] Cooldown active ({playwright_rows_left} rows left) - using Playwright directly for RecordId={record_id}", level="info")
                page_source = await fetch_via_playwright(url, headless)
                sel = Selector(text=page_source)
                # playwright_rows_left -= 1
                # if playwright_rows_left <= 0:
                    # use_playwright = False
                    # log_event("[MODE] Cooldown finished - switching back to REQUEST-first mode", level="info")
                # else:
                #     # Normal path: ALWAYS try request method first
                #     try:
                #         resp = fetch_via_requests(url)
                #         if resp.status_code == 200:
                #             sel = Selector(text=resp.text)
                #             log_event(f"[REQUEST] Using request-method content for RecordId={record_id} (status=200)", level="debug")
                            
                #         else:
                #             log_event(f"[REQUEST] Non-200 status ({resp.status_code}) for RecordId={record_id}", level="warning")
                #             request_failures += 1
                #             sel = Selector(text=resp.text)  # still parse it; might just be a non-200 error page we can check for rate limit
                #     except Exception as e:
                #         log_event(f"[REQUEST] Exception during request fetch for RecordId={record_id}: {str(e)}", level="warning")
                #         request_failures += 1
                #         sel = None  # force retry / fallback below
                
                # detect rate limiting -> this is the ONLY trigger for switching to Playwright mode
                if is_rate_limited(sel):
                    rate_limit_count += 1
                    log_event(f"[RATE-LIMIT] Detected for RecordId={record_id}. Falling back to Playwright for this record and enabling cooldown ({PLAYWRIGHT_COOLDOWN} rows).", level="warning")
                    time.sleep(random.uniform(10,30))
                    page_source = await fetch_via_playwright(url, headless)
                    sel = Selector(text=page_source)
                    use_playwright = True
                    playwright_rows_left = PLAYWRIGHT_COOLDOWN

                if sel is None:
                    # Request method raised an exception with nothing to parse - treat as a failed attempt
                    raise RuntimeError(f"Request method produced no content for RecordId={record_id}")

                items = extract_fields(sel, row)
                f_res.append(items)
                urls_dfn.loc[index, "isDone"] = "Done"
                processed_count += 1

                decedent_name = items.get('Decedent Name', 'Unknown')
                estate_num = items.get('Estate Number', 'Unknown')
                log_event(f"✓ Processed: {decedent_name} (Estate: {estate_num}, RecordId={record_id})", level="info")
                success = True
                urls_dfn.to_csv(_input_csv,index=False)
                log_event(f"File Saved")
            except Exception as e:
                error_count += 1
                retry_count += 1
                log_event(f"Error processing RecordId={record_id} (attempt {retry_count}/{MAX_RETRIES}): {str(e)}", level="error")

                if retry_count >= MAX_RETRIES:
                    # Last resort: one Playwright attempt for this specific record only.
                    # NOTE: this does NOT enable cooldown mode - only an actual
                    # rate-limit detection does that.
                    log_event(f"[FALLBACK] Request method failed {MAX_RETRIES}x for RecordId={record_id}. Trying Playwright once as a last resort.", level="warning")
                    try:
                        page_source = await fetch_via_playwright(url, headless)
                        sel = Selector(text=page_source)
                        if is_rate_limited(sel):
                            rate_limit_count += 1
                            log_event(f"[RATE-LIMIT] Detected on fallback attempt for RecordId={record_id}. Enabling cooldown ({PLAYWRIGHT_COOLDOWN} rows).", level="warning")
                            use_playwright = True
                            playwright_rows_left = PLAYWRIGHT_COOLDOWN
                        items = extract_fields(sel, row)
                        f_res.append(items)
                        urls_dfn.loc[index, "isDone"] = "Done"
                        processed_count += 1
                        log_event(f"✓ Processed via fallback Playwright: RecordId={record_id}", level="info")
                        success = True
                    except Exception as e2:
                        log_event(f"[FALLBACK] Playwright fallback also failed for RecordId={record_id}: {str(e2)}", level="error")
                        urls_dfn.loc[index, "isDone"] = "Error"
                else:
                    wait_time = random.uniform(2, 5)
                    log_event(f"Waiting {wait_time:.2f}s before retrying REQUEST method for RecordId={record_id}", level="debug")
                    await asyncio.sleep(wait_time)

        # incremental save every SAVE_EVERY records
        if len(f_res) and len(f_res) % SAVE_EVERY == 0:
            log_event(f"Checkpoint: Saving {len(f_res)} processed records", level="info")
            save_progress(f_res, urls_dfn, _input_csv)

        await asyncio.sleep(random.uniform(1, 3))

    # final save
    log_event(f"Final save: {len(f_res)} records processed", level="info")
    save_progress(f_res, urls_dfn, _input_csv)

    summary = {
        "total_processed": len(f_res),
        "errors": error_count,
        "rate_limits": rate_limit_count,
        "total_urls": total_urls,
        "range_processed": f"{start_idx}-{end_idx}",
        "request_failures": request_failures,
        "final_mode": "Playwright" if use_playwright else "Request API"
    }

    log_event("=" * 60, level="info")
    log_event("MAIN DATA SCRAPER COMPLETED", level="info")
    log_event(f"Summary: {len(f_res)} records successfully processed", level="info")
    log_event(f"Errors: {error_count}", level="info")
    log_event(f"Rate limits encountered: {rate_limit_count}", level="info")
    log_event(f"Request failures: {request_failures}", level="info")
    log_event(f"Final mode: {summary['final_mode']}", level="info")
    log_event(f"Output file: {_data_csv}", level="info")
    log_event("=" * 60, level="info")

    print(f"\n✓ Scraping Summary:")
    print(f"  • Records processed: {len(f_res)}")
    print(f"  • Errors: {error_count}")
    print(f"  • Rate limits: {rate_limit_count}")
    print(f"  • Request failures: {request_failures}")
    print(f"  • Final mode: {summary['final_mode']}")
    print(f"  • Output: {_data_csv}\n")

    # Clean up browser once at the very end (only place cleanup happens)
    await cleanup_browser()
    log_event("Browser cleaned up", level="info")

    return f_res


def run_main_data_scraper(start=None, end=None, headless=False, params=None):
    """
    Main entry point for the scraper - called from GUI.

    Args:
        start (int): Starting index for processing
        end (int): Ending index for processing
        headless (bool): Whether to run in headless mode
        params (dict): Additional parameters from the GUI

    Returns:
        dict: Results with success status, total_results, output_file, etc.
    """
    try:
        log_event("=" * 60, level="info")
        log_event("RUN_MAIN_DATA_SCRAPER CALLED", level="info")
        log_event(f"Headless parameter received: {headless} (type: {type(headless)})", level="info")

        # Ensure headless is a boolean
        if isinstance(headless, bool):
            headless_bool = headless
        else:
            # Convert to boolean if it's not already
            headless_bool = bool(headless) if headless else False
            log_event(f"Converted headless from {headless} to {headless_bool}", level="warning")

        # Get timestamp for unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Define file paths with the range and timestamp
        input_csv = os.path.join(INPUT_DIR, "estate_search_results.csv")
        data_csv = os.path.join(OUTPUT_DIR, f"Complete_data_maryland_final_{timestamp}_{start}_{end}.csv")
        status_csv = os.path.join(OUTPUT_DIR, f"final_merged_data_with_status_{timestamp}_{start}_{end}.csv")

        log_event(f"Input file: {input_csv}", level="info")
        log_event(f"Output file: {data_csv}", level="info")
        log_event(f"Status file: {status_csv}", level="info")
        log_event(f"Parameters: start={start}, end={end}, headless={headless_bool}", level="info")

        # Check if input file exists
        if not os.path.exists(input_csv):
            error_msg = f"Input file not found: {input_csv}"
            log_event(error_msg, level="error")
            return {
                "success": False,
                "error": error_msg,
                "total_results": 0,
                "output_file": None
            }

        log_event("Starting main data scraper execution", level="info")

        # Run the async scraper
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(
                run_scraper_async(start, end, input_csv, data_csv, status_csv, headless_bool)
            )
            total_results = len(results)

            log_event(f"Scraper completed successfully with {total_results} results", level="info")
            log_event(f"It's Time to clean data", level="info")
            
            process_rows(results,data_csv)
            log_event(f"Cleaning Done", level="info")

            return {
                "success": True,
                "total_results": total_results,
                "output_file": data_csv,
                "status_file": status_csv,
                "params": params
            }
        finally:
            loop.close()

    except Exception as e:
        error_msg = f"Error in run_main_data_scraper: {str(e)}"
        log_event(error_msg, level="error")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "total_results": 0,
            "output_file": None
        }


# ----------------------------------------------------------------------------
# For direct testing
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    # Test the scraper with default range
    print("Testing main data scraper...")
    log_event("TEST: Starting main data scraper test", level="info")
    result = run_main_data_scraper(start=None, end=None, headless=False)
    if result["success"]:
        print(f"✓ Success! Processed {result['total_results']} records")
        print(f"  Output file: {result['output_file']}")
        print(f"  Status file: {result['status_file']}")
        log_event(f"TEST: Success - processed {result['total_results']} records", level="info")
    else:
        print(f"✘ Failed: {result['error']}")
        log_event(f"TEST: Failed - {result['error']}", level="error")