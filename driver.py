from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import logging

logger = logging.getLogger(__name__)

def get_chrome_driver(headless=True):
    """
    Configurar y retornar driver de Chrome optimizado
    """
    chrome_options = Options()
    
    if headless:
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        chrome_options.add_argument("--disable-images")
        chrome_options.add_argument("--disable-javascript")
        chrome_options.add_argument("--disable-css")
        
    # Configuraciones para mejor rendimiento
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--allow-running-insecure-content")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--disable-features=TranslateUI")
    chrome_options.add_argument("--disable-background-timer-throttling")
    chrome_options.add_argument("--disable-backgrounding-occluded-windows")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument("--disable-field-trial-config")
    
    # User agent para evitar detección
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    
    # Configuración de ventana
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--start-maximized")
    
    # Excluir switches de automatización
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Configurar prefs para deshabilitar imágenes y mejorar velocidad
    prefs = {
        "profile.default_content_setting_values": {
            "notifications": 2,
            "images": 2,
            "plugins": 2,
            "popups": 2,
            "geolocation": 2,
            "media_stream": 2,
        },
        "profile.managed_default_content_settings": {
            "images": 2
        }
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    try:
        # Usar ChromeDriverManager para gestión automática del driver
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Configurar timeouts
        driver.implicitly_wait(10)
        driver.set_page_load_timeout(30)
        
        # Ejecutar script para evitar detección
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        logger.info(f"Driver Chrome inicializado {'en modo headless' if headless else 'con interfaz gráfica'}")
        return driver
        
    except Exception as e:
        logger.error(f"Error inicializando driver: {e}")
        raise

def get_firefox_driver(headless=True):
    """
    Alternativa con Firefox (opcional)
    """
    from selenium.webdriver.firefox.options import Options as FirefoxOptions
    from selenium.webdriver.firefox.service import Service as FirefoxService
    from webdriver_manager.firefox import GeckoDriverManager
    
    firefox_options = FirefoxOptions()
    
    if headless:
        firefox_options.add_argument("--headless")
    
    firefox_options.add_argument("--disable-gpu")
    firefox_options.add_argument("--no-sandbox")
    firefox_options.add_argument("--disable-dev-shm-usage")
    
    try:
        service = FirefoxService(GeckoDriverManager().install())
        driver = webdriver.Firefox(service=service, options=firefox_options)
        driver.implicitly_wait(10)
        driver.set_page_load_timeout(30)
        
        logger.info(f"Driver Firefox inicializado {'en modo headless' if headless else 'con interfaz gráfica'}")
        return driver
        
    except Exception as e:
        logger.error(f"Error inicializando driver Firefox: {e}")
        raise