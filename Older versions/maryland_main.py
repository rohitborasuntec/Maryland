import os
import time
import random
import requests
import pandas as pd
from parsel import Selector
from selenium import webdriver
from selenium_authenticated_proxy import SeleniumAuthenticatedProxy

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------
OUTPUT_DIR = "Output"
INPUT_CSV = os.path.join(OUTPUT_DIR, "probate_results_main_links.csv")
DATA_CSV = os.path.join(OUTPUT_DIR, "Complete_data_maryland_final.csv")
STATUS_CSV = os.path.join(OUTPUT_DIR, "final_merged_data_with_status.csv")

START = 0
END = 2000
SAVE_EVERY = 50          # write to disk after this many new records
SELENIUM_COOLDOWN = 15   # once rate-limited, stay on selenium this many rows

ip = "45.38.107.97"
port = 6014
PROXY = f"http://bnahdmpr:j3i0dsnbsfrl@{ip}:{port}/"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ----------------------------------------------------------------------------
# Selenium setup (only spun up lazily, first time it's actually needed)
# ----------------------------------------------------------------------------
_driver = None


def get_driver():
    """Create (once) and return the Selenium driver."""
    global _driver
    if _driver is None:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--enable-javascript")

        proxy_helper = SeleniumAuthenticatedProxy(proxy_url=PROXY)
        proxy_helper.enrich_chrome_options(chrome_options)

        _driver = webdriver.Chrome(options=chrome_options)
        _driver.maximize_window()
        _driver.get("https://www.google.com")
        input("Press Enter once Chrome is loaded and you have started the VPN: ")
    return _driver


def fetch_via_selenium(url):
    driver = get_driver()
    driver.get(url)
    time.sleep(random.uniform(3, 8))
    return driver.page_source


def fetch_via_requests(url):
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
        "RecordId": str(url.split("&RecordId=")[-1]),
    }
    resp = requests.get(
        "https://registers.maryland.gov/RowNetWeb/Estates/frmDocketImages.aspx",
        params=params,
        cookies=cookies,
        headers=headers,
        timeout=30,
        proxies={"http": PROXY, "https": PROXY},
    )
    return resp


def is_rate_limited(sel):
    return bool(
        sel.xpath('//*[contains(text(),"You have exceeded the allowable rate of page requests")]')
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

    items = {
        "Country": row.get("country", row.get("Country", "")),
        "Estate": row.get("estate", row.get("Estate", "")),
        "Filling Date": row.get("filling_date", ""),
        "date_of_death": row.get("date_of_death", ""),
        "Type": row.get("typee", row.get("Type", "")),
        "Status": field("Status:") or row.get("status", row.get("Status", "")),
        "Estate Number": field("Estate Number:"),
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
def save_progress(f_res, urls_dfn):
    """Overwrite both output files with current in-memory state."""
    if f_res:
        pd.DataFrame(f_res).to_csv(DATA_CSV, index=False)
    try:
        urls_dfn.to_csv(STATUS_CSV, index=False)
    except Exception as e:
        print(f"Error saving status CSV: {e}")
        urls_dfn.to_csv(os.path.join(OUTPUT_DIR, "final_merged_data_temp.csv"), index=False)


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main():
    urls_dfn = pd.read_csv(INPUT_CSV)
    if "isDone" not in urls_dfn.columns:
        urls_dfn["isDone"] = "Not Done"

    f_res = []
    total_urls = len(urls_dfn)
    print(f"Processing {total_urls} detail pages")

    use_selenium = False
    selenium_rows_left = 0

    for index, row in urls_dfn.iloc[START:END].iterrows():
        if row["isDone"] == "Done":
            print(f"Skipping already processed URL at index {index}")
            continue

        url = row["prob_link"] if "prob_link" in row and pd.notna(row.get("prob_link")) else row["link"]
        count = index + 1
        print(f"Fetching detail {count}/{total_urls}")

        try:
            if use_selenium:
                page_source = fetch_via_selenium(url)
                sel = Selector(text=page_source)
            else:
                resp = fetch_via_requests(url)
                if resp.status_code != 200:
                    print(f"Failed to fetch details for URL: {url}, status code: {resp.status_code}")
                    urls_dfn.loc[index, "isDone"] = f"Failed ({resp.status_code})"
                    continue
                sel = Selector(text=resp.text)

            # detect rate limiting and fall back to selenium for this row + a cooldown window
            if is_rate_limited(sel):
                print(f"Rate limit exceeded for URL: {url}. Retrying with Selenium.")
                page_source = fetch_via_selenium(url)
                sel = Selector(text=page_source)
                use_selenium = True
                selenium_rows_left = SELENIUM_COOLDOWN
            elif use_selenium:
                selenium_rows_left -= 1
                if selenium_rows_left <= 0:
                    use_selenium = False

            items = extract_fields(sel, row)
            f_res.append(items)
            urls_dfn.loc[index, "isDone"] = "Done"
            print(items)

        except Exception as e:
            print(f"Error processing {url}: {e}")
            urls_dfn.loc[index, "isDone"] = "Error"

        # incremental save every SAVE_EVERY records, so nothing is lost on crash
        if len(f_res) and len(f_res) % SAVE_EVERY == 0:
            save_progress(f_res, urls_dfn)

        time.sleep(random.uniform(1, 3))

    # final save, guaranteed to run whether or not we hit a SAVE_EVERY boundary
    save_progress(f_res, urls_dfn)
    print(f"Done processing detail pages. Total records: {len(f_res)}")

    if _driver is not None:
        _driver.quit()


if __name__ == "__main__":
    main()