import time, os, csv
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from driver import get_chrome_driver
from playwright.sync_api import sync_playwright
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

EMAIL = "collaguazodaniel21@gmail.com"
USERNAME = "Daniel805976894"
PASSWORD = "DaniColla2003"

print("Credenciales cargadas desde .env")
print(f"Email: {EMAIL}")
print(f"Username: {USERNAME}")
print(f"Contraseña: {PASSWORD}")

def get_headless_chrome_driver():
    """Obtener driver de Chrome en modo headless"""
    driver = get_chrome_driver()
    driver.set_window_size(1920, 1080)
    return driver

def open_twitter_login(driver):
    """Login a Twitter con manejo de errores mejorado"""
    try:
        driver.get("https://x.com/i/flow/login")
        
        email_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "text"))
        )
        email_input.send_keys(EMAIL, Keys.RETURN)
        logger.info("Email enviado")
        
        username_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "text"))
        )
        username_input.send_keys(USERNAME, Keys.RETURN)
        logger.info("Username enviado")
        
        password_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "password"))
        )
        password_input.send_keys(PASSWORD, Keys.RETURN)
        logger.info("Password enviado")
        
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//a[@href="/explore" and @role="link"]'))
        )
        logger.info("Login completado exitosamente")
        
    except Exception as e:
        logger.error(f"Error durante el login: {e}")
        raise

def go_to_explore(driver):
    """Navegar a la página de explorar"""
    try:
        explore_link = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, '//a[@href="/explore" and @role="link"]'))
        )
        explore_link.click()
        logger.info("Navegado a página de explorar")
    except Exception as e:
        logger.error(f"Error navegando a explorar: {e}")
        raise

def search_keyword(driver, keyword):
    """Buscar palabra clave en Twitter"""
    try:
        search_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//input[@data-testid="SearchBox_Search_Input"]'))
        )
        search_input.clear()
        search_input.send_keys(keyword, Keys.RETURN)
        logger.info(f"Búsqueda realizada: {keyword}")
        time.sleep(3)  # Reducido de 5 a 3 segundos
    except Exception as e:
        logger.error(f"Error en búsqueda: {e}")
        raise

def get_tweet_links(driver, max_count, extra_scrolls=4):
    """Obtener enlaces de tweets con scroll optimizado"""
    tweet_links = set()
    
    try:
        for i in range(extra_scrolls):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            logger.info(f"Scroll {i+1}/{extra_scrolls}")
            time.sleep(2)
            
            if len(tweet_links) >= max_count:
                break

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//article[@role="article"]'))
        )

        articles = driver.find_elements(By.XPATH, '//article[@role="article"]')
        
        for article in articles:
            try:
                link_elem = article.find_element(By.XPATH, './/a[contains(@href, "/status/")]')
                tweet_url = link_elem.get_attribute("href")
                if tweet_url:
                    tweet_links.add(tweet_url)
                if len(tweet_links) >= max_count:
                    break
            except:
                continue

        logger.info(f"Enlaces a tweets encontrados: {len(tweet_links)}")
        return list(tweet_links)
        
    except Exception as e:
        logger.error(f"Error obteniendo enlaces: {e}")
        return []

def scrape_tweet(url: str) -> dict:
    """
    Scrape optimizado de un tweet individual
    """
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            )
            page = context.new_page()

            _xhr_calls = []

            def intercept_response(response):
                if response.request.resource_type == "xhr":
                    _xhr_calls.append(response)

            page.on("response", intercept_response)
            page.goto(url, wait_until="networkidle")
            page.wait_for_selector("[data-testid='tweet']", timeout=30000)

            tweet_calls = [f for f in _xhr_calls if "TweetResultByRestId" in f.url]
            
            for xhr in tweet_calls:
                try:
                    data = xhr.json()
                    tweet_result = data['data']['tweetResult']['result']
                    
                    text = None
                    if 'note_tweet' in tweet_result:
                        text = tweet_result['note_tweet']['note_tweet_results']['result']['text']
                    elif 'legacy' in tweet_result:
                        text = tweet_result['legacy'].get('full_text', '')
                    
                    return {
                        "url": url,
                        "text": text,
                        "user": tweet_result.get('core', {}).get('user_results', {}).get('result', {}).get('legacy', {}).get('screen_name', ''),
                        "created_at": tweet_result.get('legacy', {}).get('created_at', ''),
                        "retweet_count": tweet_result.get('legacy', {}).get('retweet_count', 0),
                        "favorite_count": tweet_result.get('legacy', {}).get('favorite_count', 0)
                    }
                except Exception as e:
                    logger.error(f"Error procesando respuesta XHR: {e}")
                    continue
                    
            browser.close()
            return {"url": url, "text": None, "error": "No se pudo extraer el texto"}
            
    except Exception as e:
        logger.error(f"Error scrapeando tweet {url}: {e}")
        return {"url": url, "text": None, "error": str(e)}

def process_tweet_batch(tweet_links, max_workers=3, progress_callback=None):
    """Procesar tweets en lotes con threading y callback de progreso"""
    all_data = []
    completed = 0
    total = len(tweet_links)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scrape_tweet, link): idx for idx, link in enumerate(tweet_links)}
        
        for future in as_completed(futures):
            idx = futures[future]
            logger.info(f"Procesando tweet {idx + 1}/{len(tweet_links)}")
            result = future.result()
            all_data.append(result)
            completed += 1
            
            # Llamar callback de progreso si existe
            if progress_callback:
                progress_callback(completed, total)
            
    return all_data

def save_to_csv(data, filename='tweets_data.csv'):
    """Guardar datos en CSV con manejo de errores"""
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['url', 'text', 'user', 'created_at', 'retweet_count', 'favorite_count', 'error']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for row in data:
                writer.writerow(row)
                
        logger.info(f"Datos guardados en {filename}")
        
    except Exception as e:
        logger.error(f"Error guardando CSV: {e}")

def save_to_json(data, filename='tweets_data.json'):
    """Guardar datos en JSON como backup"""
    try:
        with open(filename, 'w', encoding='utf-8') as jsonfile:
            json.dump(data, jsonfile, ensure_ascii=False, indent=2)
        logger.info(f"Backup JSON guardado en {filename}")
    except Exception as e:
        logger.error(f"Error guardando JSON: {e}")

def scrape(query: str, max_results: int = 15, max_workers: int = 15):
    """
    Función principal para scrapeo de Twitter
    """
    driver = None
    
    try:
        driver = get_headless_chrome_driver()
        logger.info("Driver inicializado en modo headless")
        
        open_twitter_login(driver)
        go_to_explore(driver)
        search_keyword(driver, query)
        
        tweet_links = get_tweet_links(driver, max_results, extra_scrolls=5)
        
        if not tweet_links:
            logger.warning("No se encontraron enlaces de tweets")
            return []

        logger.info(f"Procesando {len(tweet_links)} tweets...")
        all_data = process_tweet_batch(tweet_links, max_workers)

        save_to_csv(all_data)
        save_to_json(all_data)

        successful_tweets = len([d for d in all_data if d.get('text')])
        logger.info(f"Tweets procesados exitosamente: {successful_tweets}/{len(all_data)}")

        return all_data
        
    except Exception as e:
        logger.error(f"Error en scrapeo: {e}")
        
    finally:
        if driver:
            driver.quit()
            logger.info("Driver cerrado")

def main():
    """Función principal optimizada"""
    driver = None
    
    try:
        search_term = "cuenca (protestas OR delincuencia OR seguridad OR turismo OR accidentes) since:2025-04-01"
        max_tweets = 15
        max_workers = 5
        
        driver = get_headless_chrome_driver()
        logger.info("Driver inicializado en modo headless")
        
        open_twitter_login(driver)
        go_to_explore(driver)
        search_keyword(driver, search_term)
        
        tweet_links = get_tweet_links(driver, max_tweets, extra_scrolls=5)
        
        if not tweet_links:
            logger.warning("No se encontraron enlaces de tweets")
            return

        logger.info(f"Procesando {len(tweet_links)} tweets...")
        all_data = process_tweet_batch(tweet_links, max_workers)

        save_to_csv(all_data)
        save_to_json(all_data)

        successful_tweets = len([d for d in all_data if d.get('text')])
        logger.info(f"Tweets procesados exitosamente: {successful_tweets}/{len(all_data)}")

        return all_data
        
    except Exception as e:
        logger.error(f"Error en función principal: {e}")
        
    finally:
        if driver:
            driver.quit()
            logger.info("Driver cerrado")

if __name__ == "__main__":
    main()