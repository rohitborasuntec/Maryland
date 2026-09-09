from selenium import webdriver
# import chromedriver_autoinstaller
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time,random
import requests,os
import pandas as pd
from parsel import Selector
from selenium_authenticated_proxy import SeleniumAuthenticatedProxy
from selenium.webdriver.support.ui import Select
from datetime import datetime
from dateutil.relativedelta import relativedelta

chrome_options = webdriver.ChromeOptions()
chrome_options.add_argument('--no-sandbox')
chrome_options.add_argument('--disable-dev-shm-usage')
chrome_options.add_argument("--enable-javascript")  
# chromedriver_autoinstaller.install()

PROXY = "http://vsjolrfz:w6qu4drekhnu@31.59.20.176:6754/"

proxy_helper = SeleniumAuthenticatedProxy(proxy_url=PROXY)
proxy_helper.enrich_chrome_options(chrome_options)

driver = webdriver.Chrome(options=chrome_options)
driver.maximize_window()

driver.get("https://www.google.com")
inp = input('Press Enter once date is chrome is loaded and you have to start VPN now')

estate_types = [
    "FP","MA","RE","RJ"
]

# Create the Output directory if it doesn't exist
os.makedirs("Output", exist_ok=True)

date_from = "01/01/2025"
dt = datetime.now()
date_to = (dt - relativedelta(days=1)).replace(day=1) - relativedelta(days=1)
date_to = date_to.strftime("%m/%d/%Y")

print("Date to : ",date_to)

def select_filter(estate_type):
    # estate_type 
    estate_status_select = driver.find_element(By.ID, "cboStatus")
    Select(estate_status_select).select_by_value("OPEN")
    time.sleep(2)  # Wait for the page to update after selecting the filter

    estate_select = driver.find_element(By.ID, "cboType")
    Select(estate_select).select_by_value(estate_type)
    time.sleep(2)
    estate_select = driver.find_element(By.ID, "cboPartyType")
    Select(estate_select).select_by_value("Personal Representative")
    
    time.sleep(2)  # Wait for the page to update after selecting the filter
    driver.find_element(By.ID, "DateOfFilingFrom").send_keys(date_from)
    time.sleep(2)
    driver.find_element(By.ID, "DateOfFilingTo").send_keys(date_to)
    time.sleep(2)

    driver.find_element(By.ID,"cmdSearch").click()

def grabbing_links():

    sel = Selector(text=driver.page_source)
    wait = WebDriverWait(driver, 10)
    wait.until(EC.presence_of_element_located((By.XPATH, '//table[@id="tblStatus"]//tr/td')))

    total_pge = sel.xpath('//table[@id="tblStatus"]//tr/td//text()').getall()
    final_page = "".join(total_pge).split('of')[-1].split('(')[0].strip()

    current_page = 1
    max_page = int(final_page)
    print("Total number of pages to scrape: ", max_page)
    res = []
    scraped = 0

    while current_page <= max_page:

        # ------------------- EXTRACTION PART -------------------
        for i in range(5):
            try:
                wait.until(EC.presence_of_element_located((By.ID, "dgSearchResults")))
                rows = driver.find_elements(
                    By.XPATH,
                    '(//table[@id="dgSearchResults"]/tbody/tr[@style="background-color:White;"] | '
                    '//table[@id="dgSearchResults"]/tbody/tr[@style="background-color:#EEEEEE;"])'
                )
                page_items = []
                for row in rows:
                    items = {
                        'country': row.find_element(By.XPATH, "./td[1]").text,
                        'estate': row.find_element(By.XPATH, "./td[2]/a").text,
                        'filling_date': row.find_element(By.XPATH, "./td[3]").text,
                        'date_of_death': row.find_element(By.XPATH, "./td[4]").text,
                        'typee': row.find_element(By.XPATH, "./td[5]").text,
                        'status': row.find_element(By.XPATH, "./td[6]").text,
                        'prob_link': row.find_element(By.XPATH, "./td[2]/a").get_attribute("href"),
                    }
                    page_items.append(items)

                res.extend(page_items)
                scraped += len(page_items)
                print("Success.....")
                break  # success — stop retrying extraction
            except Exception as e:
                print(f"Issue occurred on attempt {i+1}: {e}")
        else:
            print("Stale Element issue")
        # -------------------------------------------------------

        print(f"Page {current_page} done, total records so far: {scraped}")

        if current_page >= max_page:
            # last page reached, nothing more to scrape
            break

        old_table = driver.find_element(By.ID, "dgSearchResults")
        next_num = current_page + 1
        clicked = False

        try:
            # is the next page number directly clickable in the pager?
            link = driver.find_element(
                By.XPATH,
                f"//tr[@class='grid-pager']/td/a[normalize-space()='{next_num}']"
            )
            link.click()
            # clicked = True
        except Exception:
            # not directly visible — try the "..." link to reveal more page numbers
            print("Page number not found : ",next_num)
            try:
                dots = driver.find_elements(By.XPATH, "//a[contains(text(),'...')]")
                if dots:
                    dots[-1].click()
                    clicked = True
                else:
                    print(f"No '...' link found and page {next_num} not visible — stopping.")
            except Exception as e:
                print(f"Failed to click '...' link: {e}")

        if not clicked and current_page%10==0:
            print(f"Could not advance past page {current_page}. Stopping pagination.")
            break

        # wait for the old table to go stale, then for the new one to appear
        try:
            wait.until(EC.staleness_of(old_table))
        except TimeoutException:
            pass
        wait.until(EC.presence_of_element_located((By.ID, "dgSearchResults")))

        current_page += 1

    df = pd.DataFrame(res)

    return df


if __name__ == "__main__":
    # step 1: grab the listing links and write to csv
    print("Starting to grab links")
    urls_df = pd.DataFrame()
    for estate_type in estate_types:
        driver.get('https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx')
        time.sleep(random.randint(3,5))
        print(f"Processing estate type: {estate_type}")
        select_filter(estate_type)
        time.sleep(random.uniform(3, 5))  # Wait for the page to update after selecting the filter
        temp_df = grabbing_links()
        urls_df = pd.concat([urls_df, temp_df], ignore_index=True)
        urls_df.to_csv("Output/probate_results_main_links.csv", index=False, encoding="utf-8")

    print("Link data saved to probate_results_main_links.csv")

    # urls_dfn = urls_df.copy()
    # urls_dfn = pd.read_csv('Complete_data_maryland14000.csv')
    # # urls_dfn = pd.read_csv('probate_results_main_links.csv')
    # # step 2: iterate through saved links and fetch details
    # # urls_dfn = pd.read_csv('probate_results_main_links1.csv')
    # f_res = []
    # total_urls = len(urls_dfn)
    # # start = 0
    # # end = 12000
    # PROXY = "http://vsjolrfz:w6qu4drekhnu@45.38.107.97:6014/"

    # print(f"Processing {total_urls} detail pages")
    # # while urls_dfn['Status']=="":
    # urls_dfn.loc[urls_dfn['Status'].isnull(), 'Status'] = ""
    # for index, row in urls_dfn.iterrows():
    #     # simple progress indicator
    #     if row['Status'] != "":
    #         print(f"Skipping already processed URL at index {index}")
            
    #         continue
    #     count = index + 1
    #     print(f"Fetching detail {count}/{total_urls}")
    #     try:
    #         url = row["prob_link"]
    #     except :
    #         url = row["link"]
    #     cookies = {
    #         '__cf_bm': '0mKvsLm5C8OLSAXwl9HYVHvGuLhh1G.cN6Fw84c9vt8-1771821885-1.0.1.1-13Xb93ANZtk8xsfLpiGCTBadrTUZ1nO4pltZhYRTH.HQq6cbTWGKHAPOUwKdxZULNKsCHuvZBvFNvq__74_Yqrt8O4EqBAz75mn81EEZYh0',
    #         'ASP.NET_SessionId': 'j01233mbgubtnbps5qclz2i1',
    #     }

    #     headers = {
    #     'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
    #     'accept-language': 'en-US,en;q=0.9',
    #     'cache-control': 'max-age=0',
    #     'priority': 'u=0, i',
    #     'referer': 'https://registers.maryland.gov/RowNetWeb/Estates/frmEstateSearch2.aspx',
    #     'sec-ch-ua': '"Chromium";v="152", "Not?A_Brand";v="24", "Google Chrome";v="152"',
    #     'sec-ch-ua-mobile': '?0',
    #     'sec-ch-ua-platform': '"Windows"',
    #     'sec-fetch-dest': 'document',
    #     'sec-fetch-mode': 'navigate',
    #     'sec-fetch-site': 'same-origin',
    #     'sec-fetch-user': '?1',
    #     'upgrade-insecure-requests': '1',
    #     'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36',
    #     'Cookie': 'ASP.NET_SessionId=ehhqaiv50bvlknsreblu0ind'
    #     }
        
    #     params = {
    #         'src': 'row',
    #         'RecordId': str(url.split('&RecordId=')[-1]),
    #     }
        
    #     response1 = requests.get(
    #         'https://registers.maryland.gov/RowNetWeb/Estates/frmDocketImages.aspx',
    #         params=params,
    #         cookies=cookies,
    #         headers=headers,timeout=30
    #         ,proxies={"http": PROXY, "https": PROXY}
    #     )
    #     # time.sleep(random.randint(2,5))
    #     # print("Response Text {}: {}".format(url, response1.text))
    #     if response1.status_code == 200:
    #         sel = Selector(text=response1.text)
    #         items = {}
    #         items['Country'] = row.get("country",row.get("Country",""))
    #         items['Estate'] = row.get("estate",row.get("Estate",""))
    #         items['Filling Date'] = row.get("filling_date", "")
    #         items['date_of_death'] = row.get("date_of_death", "")
    #         items['Type'] = row.get("typee", row.get("Type",""))
    #         items['Status'] = row.get("status", row.get("Status",""))
    #         items['Estate Number'] = sel.xpath('//table[@id="tblEstateData"]//tr/td/span[@class="RowLabel"][contains(text(),"Estate Number:")]//following :: td/span[1]/text()').get()
    #         items['Status'] = sel.xpath('//table[@id="tblEstateData"]//tr/td/span[@class="RowLabel"][contains(text(),"Status:")]//following :: td/span[1]/text()').get()
    #         items['Decedent Name'] = sel.xpath('//table[@id="tblEstateData"]//tr/td/span[@class="RowLabel"][contains(text(),"Decedent Name:")]//following :: td/span[1]/text()').get()
    #         items['Date of Probate'] = sel.xpath('//table[@id="tblEstateData"]//tr/td/span[@class="RowLabel"][contains(text(),"Date of Probate:")]//following :: td/span[1]/text()').get()
    #         # breakpoint()
    #         per_reps = sel.xpath('//td/span[@id="lblPerReps"][contains(text(),"Personal Reps:")]/following :: span[@id="lblPersonalReps"]//text()').getall()
    #         items["Personal Reps"] = per_reps
    #         #  [cleaned for reps in per_reps if (cleaned := reps.replace("[","").replace("]","").strip())]
    #         # for i, per in enumerate(per_reps):
    #         #     name = per_reps
    #         # name = per_reps[0].spl
    #         # items[f"Personal Rep{i+1}_First_Name"] = 
    #         #     items[f"Personal Rep{i+1}_Last_Name"] = 
    #         items['Attorney'] = sel.xpath('//td/span[@id="Label1"][contains(text(),"Attorney:")]/following :: td/span[@id="lblAttorney"]//text()').getall()
    #         items['Date Opened'] = sel.xpath('//td/span[@id="Label14"][contains(text(),"Date Opened:")]/following :: td/span[@id="lblDateOpened"]//text()').get()
    #         items['Date of Filing'] = sel.xpath('//td/span[@id="Label16"][contains(text(),"Date of Filing:")]/following :: td/span[@id="lblDateOfFiling"]//text()').get()
    #         items['Date of Will'] = sel.xpath('//td/span[@id="Label17"][contains(text(),"Date of Will:")]/following :: td/span[@id="lblDateOfWill"]//text()').get()
    #         items['link'] = row.get("prob_link", row.get("link", ""))
    #         try:
    #             for key in items.keys():
    #                 urls_dfn.loc[index, key] = items[key]
    #                 # urls_dfn.loc[index, 'Status'] = "Done"
    #         except Exception as e:
    #             print(f"Error occurred while processing row {index}: {e}")  
    #         f_res.append(items)
    #         print(items)
    #         # write incrementally every 50 items to avoid data loss
    #         if len(f_res) % 50 == 0 or count == total_urls:
                
    #             f_dfn = pd.DataFrame(f_res)
    #             header = False if count != 50 else True
    #             f_dfn.to_csv(f'Complete_data_maryland_final1.csv', index=False, mode='a', header=header)
    #             urls_dfn.to_csv('Complete_data_maryland_full_final.csv', index=False)
    #     else:
    #         print(f"Failed to fetch details for URL: {url}, status code: {response1.status_code}")
    # f_dfn.to_csv(f'Complete_data_maryland_final1.csv', index=False, mode='a', header=header)
    # urls_dfn.to_csv('Complete_data_maryland_full_final.csv', index=False)
    # print(f"Done processing detail pages. Total records: {len(f_res)}")
    # # driver.quit()


