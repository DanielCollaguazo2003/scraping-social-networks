from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from webdriver_manager.chrome import ChromeDriverManager

def get_chrome_driver():
    """
    Inicializa y retorna una nueva instancia de ChromeDriver con una sesión limpia.
    """
    options = ChromeOptions()
    
    # Comenta o elimina las siguientes líneas para ejecutar Chrome con GUI:
    # options.add_argument("--headless")
    
    # Estas opciones ayudan a evitar errores comunes en Linux
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    
    # Abrir siempre una nueva ventana de perfil temporal
    options.add_argument("--incognito")
    options.add_argument("--start-maximized")

    # Evita que Selenium sea detectado (opcional)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    service = ChromeService(executable_path=ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Opcional: desactiva la detección automática de Selenium en el navegador
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    return driver