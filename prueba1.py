from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time

# Configura el navegador
options = Options()
# options.add_argument("--headless")  # Puedes activarlo si ya no necesitas ver la ventana
driver = webdriver.Chrome(options=options)

# Abre la página de login
driver.get("https://x.com/i/flow/login")
time.sleep(5)

# Encuentra el input del correo o usuario
username_input = driver.find_element(By.TAG_NAME, "input")
username_input.send_keys("collaguazodaniel21@gmail.com")
username_input.send_keys(Keys.ENTER)
time.sleep(5)

# Encuentra el input de la contraseña
password_input = driver.find_element(By.NAME, "password")
password_input.send_keys("DaniColla2003")
password_input.send_keys(Keys.ENTER)
time.sleep(5)

# Captura pantalla después del login
driver.save_screenshot("logged_in.png")

driver.quit()
