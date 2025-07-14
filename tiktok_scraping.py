import os
import time
import csv
import json
import random
import re
import unicodedata
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException
from urllib.parse import quote
import logging
import undetected_chromedriver as uc

class TikTokScraper:
    def __init__(self):
        self.driver = None
        self.setup_logging()
        self.setup_directories()
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0'
        ]
        
        # Configuración para limpieza de texto
        self.keywords_turismo = [
            "tour", "paseo", "guia", "viaje", "turismo", "excursion",
            "precio", "costo", "horario", "informacion", "visita", "lugar",
            "sitio", "hermoso", "bonito", "recomiendo", "destino", "agencia",
            "hotel", "hospedaje", "transporte", "ruta", "conocer", "termales", "playa", "montana"
        ]
        
        self.palabras_feas = [
            "mierda", "puta", "puto", "maldito", "idiota", "pendejo", "coño", "culero",
            "estupido", "imbecil", "marica", "hijueputa", "cabron", "hdp", "perra"
        ]
        
        self.regex_emojis = re.compile("[" 
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F300-\U0001F5FF"
            "\U0001F680-\U0001F6FF"
            "\U0001F1E0-\U0001F1FF"
            "\U00002500-\U00002BEF"
            "\U00002702-\U000027B0"
            "\U000024C2-\U0001F251"
            "]+", flags=re.UNICODE)
        
        self.regex_url = re.compile(r'https?://\S+|www\.\S+')
        self.regex_mencion = re.compile(r'@\w+')
        
    def setup_logging(self):
        """Configura el sistema de logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('tiktok_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def setup_directories(self):
        """Crea los directorios necesarios"""
        directories = ['comentarios', 'resultados', 'limpieza']
        for directory in directories:
            if not os.path.exists(directory):
                os.makedirs(directory)
                self.logger.info(f"Directorio '{directory}' creado")
    
    def setup_driver(self):
        """Configura el driver usando undetected-chromedriver"""
        try:
            options = uc.ChromeOptions()
            
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--start-maximized')
            
            user_agent = random.choice(self.user_agents)
            options.add_argument(f'--user-agent={user_agent}')
            
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--disable-web-security')
            options.add_argument('--allow-running-insecure-content')
            options.add_argument('--disable-extensions')
            
            prefs = {
                "profile.default_content_setting_values.notifications": 2,
                "profile.default_content_settings.popups": 0,
                "profile.managed_default_content_settings.images": 1,
                "profile.default_content_setting_values.media_stream_mic": 2,
                "profile.default_content_setting_values.media_stream_camera": 2,
                "profile.default_content_setting_values.geolocation": 2,
            }
            options.add_experimental_option("prefs", prefs)
            
            self.driver = uc.Chrome(options=options, version_main=None)
            
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            self.driver.execute_script("Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]})")
            self.driver.execute_script("Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})")
            
            self.logger.info("Driver configurado exitosamente con undetected-chromedriver")
            
        except Exception as e:
            self.logger.error(f"Error al configurar el driver: {e}")
            raise
    
    def human_like_scroll(self, duration=3, direction='down'):
        """Simula scroll más humano con variaciones"""
        try:
            start_time = time.time()
            while time.time() - start_time < duration:
                scroll_amount = random.randint(100, 300)
                if direction == 'down':
                    self.driver.execute_script(f"window.scrollBy(0, {scroll_amount});")
                else:
                    self.driver.execute_script(f"window.scrollBy(0, -{scroll_amount});")
                
                time.sleep(random.uniform(0.5, 1.5))
                
        except Exception as e:
            self.logger.warning(f"Error en scroll humano: {e}")
    
    def random_mouse_movement(self):
        """Simula movimientos aleatorios del mouse"""
        try:
            action = ActionChains(self.driver)
            
            window_size = self.driver.get_window_size()
            width = window_size['width']
            height = window_size['height']
            
            for _ in range(3):
                x = random.randint(0, width)
                y = random.randint(0, height)
                action.move_by_offset(x, y)
                time.sleep(random.uniform(0.5, 1.0))
                
            action.perform()
            
        except Exception as e:
            self.logger.warning(f"Error en movimiento del mouse: {e}")
    
    def detect_captcha(self):
        """Detecta si hay un CAPTCHA presente"""
        captcha_selectors = [
            '#captcha-verify-container',
            '#captcha-verify-container-main-page',
            '.captcha-verify-container',
            '[data-testid="captcha"]',
            '.secsdk-captcha-drag-icon'
        ]
        
        for selector in captcha_selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    self.logger.warning(f"CAPTCHA detectado con selector: {selector}")
                    return True
            except:
                continue
        
        return False
    
    def handle_captcha(self):
        """Maneja el CAPTCHA cuando aparece"""
        self.logger.info("Intentando manejar CAPTCHA...")
        
        time.sleep(random.uniform(10, 20))
        
        self.random_mouse_movement()
        
        try:
            close_button = self.driver.find_element(By.ID, 'captcha_close_button')
            if close_button:
                close_button.click()
                time.sleep(3)
                return True
        except:
            pass
        
        try:
            refresh_button = self.driver.find_element(By.ID, 'captcha_refresh_button')
            if refresh_button:
                refresh_button.click()
                time.sleep(5)
                return True
        except:
            pass
        
        self.logger.info("Navegando a página principal para evitar CAPTCHA...")
        self.driver.get('https://www.tiktok.com')

        time.sleep(random.uniform(5, 10))
        
        self.human_like_scroll(duration=5)
        
        return False
    
    def wait_and_retry(self, max_retries=3):
        """Espera y reintenta si hay CAPTCHA"""
        for attempt in range(max_retries):
            if self.detect_captcha():
                self.logger.warning(f"CAPTCHA detectado. Intento {attempt + 1}/{max_retries}")
                if self.handle_captcha():
                    time.sleep(random.uniform(5, 10))
                    continue
                else:
                    wait_time = random.uniform(30, 60) * (attempt + 1)
                    self.logger.info(f"Esperando {wait_time:.1f} segundos antes del siguiente intento...")
                    time.sleep(wait_time)
            else:
                return True
        
        return False
    
    def search_videos(self, keyword, num_videos=5):
        """Busca videos en TikTok con medidas anti-CAPTCHA"""
        try:
            self.logger.info("Navegando a página principal de TikTok...")
            self.driver.get('https://www.tiktok.com')
            time.sleep(random.uniform(5, 10))
            
            if not self.wait_and_retry():
                self.logger.error("No se pudo superar el CAPTCHA inicial")
                return []
            
            self.human_like_scroll(duration=3)
            
            search_url = f"https://www.tiktok.com/search?q={quote(keyword)}"
            self.logger.info(f"Buscando videos con palabra clave: {keyword}")
            
            self.driver.get(search_url)
            time.sleep(random.uniform(8, 15))
            
            if not self.wait_and_retry():
                self.logger.error("No se pudo superar el CAPTCHA en búsqueda")
                return []
            
            self.logger.info("Cargando videos con scroll gradual...")
            for i in range(7):
                self.human_like_scroll(duration=2)
                time.sleep(random.uniform(2, 4))
                self.logger.info(f"Scroll {i+1} completado")
                
                if self.detect_captcha():
                    if not self.wait_and_retry():
                        break
            
            videos_data = []
            
            selectors = [
                'div[data-e2e="search-video-item"]',
                'div[data-e2e="search_top-item"]',
                'div[data-e2e="search-card-video"]',
                'div[data-e2e="search-card-item"]',
                'div[class*="DivItemContainer"]',
                'div[class*="video-feed-item"]',
                'a[href*="/video/"]'
            ]
            
            video_elements = []
            for selector in selectors:
                try:
                    elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    self.logger.info(f"Selector '{selector}': {len(elements)} elementos encontrados")
                    if elements:
                        video_elements = elements
                        break
                except Exception as e:
                    self.logger.warning(f"Error con selector '{selector}': {e}")
                    continue
            
            valid_videos = []
            for element in video_elements:
                try:
                    link = element.find_element(By.TAG_NAME, 'a')
                    href = link.get_attribute('href')
                    if href and 'tiktok.com' in href and '/video/' in href:
                        valid_videos.append(element)
                except:
                    continue
            
            self.logger.info(f"Encontrados {len(valid_videos)} videos válidos")
            
            for i, video_element in enumerate(valid_videos[:num_videos]):
                try:
                    video_data = self.extract_video_info(video_element, i+1)
                    if video_data:
                        videos_data.append(video_data)
                        self.logger.info(f"Video {i+1} extraído: {video_data['usuario']}")
                    
                    time.sleep(random.uniform(1, 3))
                    
                except Exception as e:
                    self.logger.warning(f"Error al extraer video {i+1}: {e}")
                    continue
            
            return videos_data
            
        except Exception as e:
            self.logger.error(f"Error en búsqueda de videos: {e}")
            return []
    
    def extract_video_info(self, video_element, video_num):
        """Extrae información básica de un video"""
        try:
            video_url = None
            try:
                link_element = video_element.find_element(By.TAG_NAME, 'a')
                video_url = link_element.get_attribute('href')
            except:
                try:
                    video_url = video_element.get_attribute('href')
                except:
                    pass
            
            if not video_url or 'tiktok.com' not in video_url:
                return None
            
            usuario = "Usuario perdido"
            user_selectors = [
                'span[data-e2e="search-card-user-unique-id"]',
                'span[data-e2e="browse-video-owner"]',
                'span[class*="username"]',
                'span[class*="user"]',
                'p[class*="user"]'
            ]
            
            for selector in user_selectors:
                try:
                    user_element = video_element.find_element(By.CSS_SELECTOR, selector)
                    usuario = user_element.text.strip()
                    if usuario:
                        break
                except:
                    continue
            
            descripcion = "Descripción no disponible"
            desc_selectors = [
                'div[data-e2e="search-card-desc"]',
                'div[data-e2e="browse-video-desc"]',
                'div[class*="desc"]',
                'p[class*="desc"]'
            ]
            
            for selector in desc_selectors:
                try:
                    desc_element = video_element.find_element(By.CSS_SELECTOR, selector)
                    descripcion = desc_element.text.strip()
                    if descripcion:
                        break
                except:
                    continue
            
            if descripcion == "Descripción no disponible":
                try:
                    text = video_element.text.strip()
                    if text and len(text) > 10:
                        descripcion = text[:100] + "..."
                except:
                    pass
            
            return {
                'numero': video_num,
                'usuario': usuario,
                'descripcion': descripcion,
                'url': video_url
            }
            
        except Exception as e:
            self.logger.error(f"Error al extraer información del video: {e}")
            return None
    
    def extract_comments(self, video_url, video_num):
        """Extrae comentarios con protección anti-CAPTCHA"""
        try:
            self.logger.info(f"Extrayendo comentarios del video {video_num}")
            self.driver.get(video_url)
            try:
                body = self.driver.find_element(By.TAG_NAME, 'body')
                body.send_keys(Keys.SPACE)
                self.logger.info("Video pausado con tecla SPACE")
                time.sleep(1)
            except Exception as e:
                self.logger.warning(f"No se pudo pausar el video: {e}")

            time.sleep(random.uniform(5, 10))
            
            if not self.wait_and_retry():
                self.logger.error("No se pudo superar CAPTCHA al cargar video")
                return []
            
            for i in range(5):
                self.human_like_scroll(duration=2)
                time.sleep(random.uniform(2, 4))
                
                if self.detect_captcha():
                    if not self.wait_and_retry():
                        break
            
            comment_selectors = [
                'p[data-e2e="comment-level-1"]',
                'span[data-e2e="comment-level-1"]',
                'div[data-e2e="comment-level-1"]',
                'p[class*="comment"]',
                'span[class*="comment"]'
            ]
            
            comments = []
            for selector in comment_selectors:
                try:
                    comment_elements = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if comment_elements:
                        self.logger.info(f"Encontrados {len(comment_elements)} comentarios con selector: {selector}")
                        break
                except:
                    continue
            
            for i, comment_element in enumerate(comment_elements):
                try:
                    comment_text = comment_element.text.strip()
                    if comment_text and len(comment_text) > 2:
                        comments.append({
                            'numero': i + 1,
                            'texto': comment_text,
                            'timestamp': datetime.now().isoformat()
                        })
                    
                except Exception as e:
                    self.logger.warning(f"Error al extraer comentario {i+1}: {e}")
                    continue
            
            self.logger.info(f"Extraídos {len(comments)} comentarios del video {video_num}")
            return comments
            
        except Exception as e:
            self.logger.error(f"Error al extraer comentarios: {e}")
            return []
    
    def save_comments_to_txt(self, comments, video_data):
        """Guarda los comentarios en un archivo .txt"""
        try:
            filename = f"comentarios/video_{video_data['numero']}_{video_data['usuario']}.txt"
            filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_', '/', '.')).rstrip()
            
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(f"=== COMENTARIOS DEL VIDEO {video_data['numero']} ===\n")
                f.write(f"Usuario: {video_data['usuario']}\n")
                f.write(f"Descripción: {video_data['descripcion']}\n")
                f.write(f"URL: {video_data['url']}\n")
                f.write(f"Fecha de extracción: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total de comentarios: {len(comments)}\n")
                f.write("=" * 50 + "\n\n")
                
                for comment in comments:
                    f.write(f"COMENTARIO {comment['numero']}:\n")
                    f.write(f"Texto: {comment['texto']}\n")
                    f.write(f"Timestamp: {comment['timestamp']}\n")
                    f.write("-" * 30 + "\n")
            
            self.logger.info(f"Comentarios guardados en: {filename}")
            
        except Exception as e:
            self.logger.error(f"Error al guardar comentarios en .txt: {e}")
    
    def save_results_to_csv(self, videos_data, keyword):
        """Guarda los resultados en un archivo CSV"""
        try:
            filename = f"resultados/tiktok_scraping_{keyword}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['numero', 'usuario', 'descripcion', 'url', 'total_comentarios']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                for video in videos_data:
                    writer.writerow(video)
            
            self.logger.info(f"Resultados guardados en CSV: {filename}")
            
        except Exception as e:
            self.logger.error(f"Error al guardar CSV: {e}")
    
    # Métodos para limpieza de texto
    def limpiar_texto(self, texto: str) -> str:
        """Limpia el texto eliminando emojis, URLs, menciones y palabras ofensivas"""
        texto = self.regex_emojis.sub('', texto)
        texto = self.regex_url.sub('', texto)
        texto = self.regex_mencion.sub('', texto)
        texto = unicodedata.normalize("NFD", texto)
        texto = texto.encode("ascii", "ignore").decode("utf-8")
        palabras = texto.split()
        limpio = [p for p in palabras if p.lower() not in self.palabras_feas]
        return " ".join(limpio)

    def detectar_keywords(self, texto_limpio: str):
        """Detecta keywords turísticas en el texto"""
        palabras = texto_limpio.lower().split()
        keywords = sorted(set(p for p in palabras if p in self.keywords_turismo))
        return keywords if keywords else ["no_relacionado"]

    def limpiar_archivo(self, origen_path, destino_path, csv_writer):
        """Limpia un archivo de comentarios individual"""
        with open(origen_path, "r", encoding="utf-8") as f:
            lineas = f.readlines()

        nuevas_lineas = []
        usuario = "Usuario desconocido"
        url = ""
        descripcion = ""
        comentarios_limpios = []

        for linea in lineas:
            if linea.startswith("Usuario:"):
                usuario = linea.replace("Usuario:", "").strip()
                nuevas_lineas.append(linea)
            elif linea.startswith("URL:"):
                url = linea.replace("URL:", "").strip()
                nuevas_lineas.append(linea)
            elif linea.startswith("Descripción:"):
                descripcion = linea.replace("Descripción:", "").strip()
                nuevas_lineas.append(linea)
            elif linea.startswith("Texto:"):
                original = linea.replace("Texto:", "").strip()
                limpio = self.limpiar_texto(original)
                nuevas_lineas.append(f"Texto: {limpio}\n")
                comentarios_limpios.append(limpio)

                # Detectar keywords turísticas
                keywords = self.detectar_keywords(limpio)
                csv_writer.writerow({
                    'usuario': usuario,
                    'comentario': limpio,
                    'keywords_detectadas': ", ".join(keywords)
                })
            else:
                nuevas_lineas.append(linea)

        with open(destino_path, "w", encoding="utf-8") as f:
            f.writelines(nuevas_lineas)
        
        # Retornar datos para JSON
        return {
            'url': url,
            'content': " ".join(comentarios_limpios)
        }

    def procesar_limpieza(self, keyword):
        """Procesa todos los archivos de comentarios y genera archivos limpios"""
        carpeta_origen = "comentarios"
        carpeta_destino = "limpieza"
        
        csv_filename = f"turismo_keywords_{keyword}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        json_filename = f"videos_content_{keyword}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        videos_json_data = []
        
        with open(csv_filename, "w", newline='', encoding="utf-8") as csvfile:
            fieldnames = ["usuario", "comentario", "keywords_detectadas"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()

            for archivo in os.listdir(carpeta_origen):
                if archivo.endswith(".txt") and "video_" in archivo:
                    origen = os.path.join(carpeta_origen, archivo)
                    destino = os.path.join(carpeta_destino, archivo)
                    self.logger.info(f"🧼 Limpiando y extrayendo de: {archivo}")
                    
                    video_data = self.limpiar_archivo(origen, destino, writer)
                    if video_data['url'] and video_data['content']:
                        videos_json_data.append(video_data)
        
        # Guardar JSON
        with open(json_filename, 'w', encoding='utf-8') as json_file:
            json.dump(videos_json_data, json_file, ensure_ascii=False, indent=2)
        
        self.logger.info(f"✅ Limpieza completada.")
        self.logger.info(f"📁 Archivos limpiados en: {carpeta_destino}")
        self.logger.info(f"📊 CSV generado: {csv_filename}")
        self.logger.info(f"🗂️ JSON generado: {json_filename}")
    
    def run_scraping(self, keyword, num_videos=5):
        """Ejecuta el proceso completo de scraping con limpieza automática"""
        try:
            self.logger.info(f"Iniciando scraping para '{keyword}' con {num_videos} videos")
            
            self.setup_driver()
            
            videos_data = self.search_videos(keyword, num_videos)
            
            if not videos_data:
                self.logger.warning("No se encontraron videos")
                return
            
            self.logger.info(f"Encontrados {len(videos_data)} videos, extrayendo comentarios de todos...")
            
            # Extraer comentarios de todos los videos automáticamente
            for video_data in videos_data:
                comments = self.extract_comments(video_data['url'], video_data['numero'])
                video_data['total_comentarios'] = len(comments)
                
                self.save_comments_to_txt(comments, video_data)
                
                time.sleep(random.uniform(5, 10))
            
            self.save_results_to_csv(videos_data, keyword)
            
            self.logger.info("Scraping completado, iniciando limpieza...")
            
            # Procesar limpieza automáticamente
            self.procesar_limpieza(keyword)
            
            self.logger.info("Proceso completo finalizado exitosamente")
            
        except Exception as e:
            self.logger.error(f"Error durante el scraping: {e}")
        finally:
            self.close_driver()
    
    def close_driver(self):
        """Cierra el driver del navegador"""
        if self.driver:
            self.driver.quit()
            self.logger.info("Driver cerrado")

def main():
    """Función principal simplificada"""
    print("🤖 TikTok Scraper con Limpieza Automática")
    print("=" * 50)
    print("NOTA: Este scraper incluye medidas anti-CAPTCHA y limpieza automática")
    print("Se extraerán comentarios de TODOS los videos encontrados")
    print("=" * 50)
    
    keyword = input("Ingresa término de búsqueda: ").strip()
    if not keyword:
        print("❌ Debes ingresar un término de búsqueda")
        return
    
    try:
        num_videos = int(input("¿Cuántos videos quieres analizar? (máx 10 recomendado): "))
        if num_videos > 20:
            num_videos = 20
            print("⚠️ Limitado a 20 videos máximo")
        elif num_videos < 1:
            num_videos = 5
            print("⚠️ Mínimo 1 video, establecido a 5")
    except ValueError:
        num_videos = 5
        print("⚠️ Valor inválido, establecido a 5 videos")
    
    scraper = TikTokScraper()
    scraper.run_scraping(keyword, num_videos)

if __name__ == "__main__":
    main()