import time, os, csv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver import get_chrome_driver
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor, as_completed

EMAIL = ""
USERNAME = ""
PASSWORD = ""

def open_twitter_login(driver):
    driver.get("https://x.com/i/flow/login")
    time.sleep(3)
    driver.find_element(By.NAME, "text").send_keys(EMAIL, Keys.RETURN)
    time.sleep(3)
    driver.find_element(By.NAME, "text").send_keys(USERNAME, Keys.RETURN)
    time.sleep(3)
    driver.find_element(By.NAME, "password").send_keys(PASSWORD, Keys.RETURN)
    time.sleep(5)
    print("Sesión iniciada")

def go_to_explore(driver):
    WebDriverWait(driver, 15).until(
        EC.element_to_be_clickable((By.XPATH, '//a[@href="/explore" and @role="link"]'))
    ).click()
    print("Sección 'Explorar' lista")

def search_keyword(driver, keyword):
    search_input = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, '//input[@data-testid="SearchBox_Search_Input"]'))
    )
    search_input.clear()
    search_input.send_keys(keyword, Keys.RETURN)
    print(f"Búsqueda de: {keyword}")
    time.sleep(5)

def get_tweet_articles(driver, max_count):
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.XPATH, '//article[@role="article"]')))
    articles = driver.find_elements(By.XPATH, '//article[@role="article"]')
    return articles[:max_count]

def get_tweet_links(driver, max_count, extra_scrolls=4):
    for i in range(extra_scrolls):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        print(f"Scroll ({i+1}/{extra_scrolls})")
        time.sleep(2.5)

    WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, '//article[@role="article"]'))
    )

    articles = driver.find_elements(By.XPATH, '//article[@role="article"]')
    tweet_links = []

    for article in articles:
        try:
            link_elem = article.find_element(By.XPATH, './/a[contains(@href, "/status/")]')
            tweet_url = link_elem.get_attribute("href")
            if tweet_url and tweet_url not in tweet_links:
                tweet_links.append(tweet_url)
            if len(tweet_links) >= max_count:
                break
        except:
            continue

    print(f"Enlaces a tweets encontrados: {len(tweet_links)}")
    return tweet_links

def scrape_tweet(url: str) -> dict:
    """
    Scrape a single tweet page for Tweet thread e.g.:
    https://twitter.com/Scrapfly_dev/status/1667013143904567296
    Return parent tweet, reply tweets and recommended tweets
    """
    _xhr_calls = []

    def intercept_response(response):
        """capture all background requests and save them"""
        # we can extract details from background requests
        if response.request.resource_type == "xhr":
            _xhr_calls.append(response)
        return response

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # enable background request intercepting:
        page.on("response", intercept_response)
        # go to url and wait for the page to load
        page.goto(url)
        page.wait_for_selector("[data-testid='tweet']")

        # find all tweet background requests:
        tweet_calls = [f for f in _xhr_calls if "TweetResultByRestId" in f.url]
        for xhr in tweet_calls:
            data = xhr.json()
            return data['data']['tweetResult']['result']

def process_tweet(link):
    try:
        tweet = scrape_tweet(link)
        text = tweet['note_tweet']['note_tweet_results']['result']['text']
        return {"link": link, "text": text}
    except Exception as e:
        print(f"Error procesando {link}: {e}")
        return {"link": link, "text": None}

if __name__ == "__main__":
    driver = get_chrome_driver()
    all_data = []
    
    try:
        open_twitter_login(driver)
        go_to_explore(driver)
        search_keyword(driver, "#cuenca, cuenca")
        time.sleep(5)

        tweet_links = get_tweet_links(driver, 100, extra_scrolls=4)

        for idx, link in enumerate(tweet_links):
            print(f"\nProcesando tweet {idx + 1}/{len(tweet_links)}")
            print(link)
            tweet = scrape_tweet(link)
            text = tweet['note_tweet']['note_tweet_results']['result']['text']
            
            all_data.append({
                "link": link,
                "text": text
            })

        # with ThreadPoolExecutor(max_workers=max_workers) as executor:
        #     futures = {executor.submit(process_tweet, link): idx for idx, link in enumerate(tweet_links)}
            
        #     for future in as_completed(futures):
        #         idx = futures[future]
        #         print(f"\nProcesando tweet {idx + 1}/{len(tweet_links)}")
        #         result = future.result()
        #         print(result["link"])
        #         all_data.append(result)

        with open('tweets_data.csv', 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['link', 'text']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for data in all_data:
                writer.writerow(data)
    finally:
        driver.quit()

    print(all_data)

