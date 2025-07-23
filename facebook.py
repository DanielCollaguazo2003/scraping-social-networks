import asyncio
import json
import re
import os
import unicodedata
from datetime import datetime
from playwright.async_api import async_playwright
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def normalizar_texto(texto):
    """Normaliza el texto eliminando caracteres especiales y convirtiendo a ASCII cuando sea posible"""
    if not texto:
        return ""
    
    # Normalizar caracteres Unicode
    texto = unicodedata.normalize('NFKD', texto)
    
    # Convertir a ASCII ignorando caracteres no convertibles
    texto = texto.encode('ascii', 'ignore').decode('ascii')
    
    # Reemplazar caracteres especiales comunes
    reemplazos = {
        '"': '"', '"': '"', ''': "'", ''': "'", '—': '-', '–': '-',
        '…': '...', '•': '*', '→': '->', '←': '<-', '↑': '^', '↓': 'v',
        '€': 'EUR', '£': 'GBP', '¥': 'JPY', '°': ' grados', '±': '+/-',
        '×': 'x', '÷': '/', '™': 'TM', '®': 'R', '©': 'C', '¡': '!',
        '¿': '?', 'ñ': 'n', 'Ñ': 'N', 'á': 'a', 'é': 'e', 'í': 'i',
        'ó': 'o', 'ú': 'u', 'Á': 'A', 'É': 'E', 'Í': 'I', 'Ó': 'O',
        'Ú': 'U', 'ü': 'u', 'Ü': 'U'
    }
    
    for original, reemplazo in reemplazos.items():
        texto = texto.replace(original, reemplazo)
    
    return texto

def limpiar_comentario_facebook(texto_completo):
    if not texto_completo:
        return ""
    
    texto_limpio = normalizar_texto(texto_completo).strip()
    
    # Eliminar nombres al inicio
    patron_nombre = r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)*\s*'
    texto_sin_nombre = re.sub(patron_nombre, '', texto_limpio)
    
    # Patrones para eliminar fechas y timestamps
    patrones_tiempo = [
        r'\d+\s*(ano|anos|year|years|mes|meses|month|months|semana|semanas|week|weeks|sem|min|h|dia|dias|day|days|hour|hours|minute|minutes|ago)\s*',
        r'hace\s+\d+\s*(minutos?|horas?|dias?|semanas?|meses?|anos?)\s*',
        r'\d+\s*(minutes?|hours?|days?|weeks?|months?|years?)\s+ago\s*',
        r'\b\d{1,2}\s+de\s+\w+\s+de\s+\d{4}\b',
        r'\b\d{1,2}/\d{1,2}/\d{2,4}\b',
        r'\b\d{4}-\d{1,2}-\d{1,2}\b',
        r'\d+\s*(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre)\s*',
        r'\d+\s*(january|february|march|april|may|june|july|august|september|october|november|december)\s*',
        r'\d+\s*$',
    ]
    
    # Patrones para eliminar elementos de UI
    patrones_ui = [
        r'(me gusta|like|responder|reply|compartir|share|editado|edited)(\s*\d+)?.*$',
        r'(seguir|follow|unfollow|ver mas|see more|mostrar menos|show less)',
        r'(traducir|translate|ver traduccion|see translation)',
        r'(ocultar|hide|reportar|report|bloquear|block)',
        r'^\s*\.\s*$', r'^\s*\|+\s*$', r'^\s*-+\s*$',
    ]
    
    # Aplicar limpieza
    for patron in patrones_tiempo + patrones_ui:
        texto_sin_nombre = re.sub(patron, '', texto_sin_nombre, flags=re.IGNORECASE)
    
    # Limpiar espacios múltiples y caracteres especiales
    texto_final = re.sub(r'\s+', ' ', texto_sin_nombre)
    texto_final = re.sub(r'[^\w\s.,!?;:()\-\'"]', '', texto_final)
    texto_final = texto_final.strip()
    
    return texto_final

def contiene_solo_stickers_o_emojis(texto):
    if not texto or not texto.strip():
        return True
    
    texto_limpio = texto.strip()
    
    # Eliminar emojis comunes representados como texto
    patrones_stickers = [
        r':\w+:', r'<\w+>', r'\[\w+\]', r'{\w+}', r'sticker',
        r'gif\s*animado', r'imagen\s*animada',
        r'^\s*[!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]*\s*$',
        r'^\s*[0-9\s\.\,\!\?\-\+\*\/\=\(\)\[\]\{\}]*\s*$'
    ]
    
    for patron in patrones_stickers:
        if re.match(patron, texto_limpio, flags=re.IGNORECASE):
            return True
    
    # Verificar si solo contiene caracteres repetidos
    texto_sin_espacios = re.sub(r'\s+', '', texto_limpio)
    if len(set(texto_sin_espacios)) < 2:
        return True
    
    return False

def es_comentario_valido(texto):
    if not texto or not texto.strip() or len(texto.strip()) < 3:
        return False
    
    texto_limpio = texto.strip()
    
    if contiene_solo_stickers_o_emojis(texto_limpio):
        return False
    
    # Verificar que tenga al menos 2 letras consecutivas
    if not re.search(r'[a-zA-Z]{2,}', texto_limpio):
        return False
    
    # Eliminar comentarios que son solo menciones o hashtags
    if re.match(r'^@\w+(\s+@\w+)*\s*$', texto_limpio):
        return False
    
    if re.match(r'^#\w+(\s+#\w+)*\s*$', texto_limpio):
        return False
    
    # Eliminar comentarios muy cortos que no aportan valor
    if len(texto_limpio.split()) < 2:
        return False
    
    return True

async def es_video_o_short(publicacion):
    indicadores_video = [
        "video", "div[data-testid='video-player']", "video[data-testid]",
        "div[aria-label*='video' i]", "div[aria-label*='reel' i]",
        "div[aria-label*='short' i]", "div[data-testid='reel']",
        "div[data-testid='short']", "div[class*='video']",
        "div[class*='reel']", "div[class*='short']",
        "button[aria-label*='play' i]", "button[aria-label*='reproducir' i]",
        "div[role='button'][aria-label*='video' i]",
        "svg[aria-label*='play' i]", "svg[aria-label*='reproducir' i]"
    ]
    
    for selector in indicadores_video:
        try:
            if await publicacion.locator(selector).count() > 0:
                return True
        except:
            continue
    
    return False

async def tiene_descripcion_suficiente(publicacion):
    selectores_texto = [
        "div[dir='auto']", "span[dir='auto']",
        "div[data-testid='post_message']", "div[data-ad-preview='message']"
    ]
    
    for selector in selectores_texto:
        elementos = publicacion.locator(selector)
        if await elementos.count() > 0:
            textos = await elementos.all_text_contents()
            texto_combinado = ' '.join(textos).strip()
            
            if len(texto_combinado.split()) >= 5:
                return True
    
    return False

async def buscar_boton_comentar(publicacion):
    selectores_boton = [
        'div[aria-label="Dejar un comentario"]',
        'span[data-ad-rendering-role="comment_button"]',
        'div[role="button"] >> text=Comentar',
        'div[role="button"][aria-label*="comentar" i]',
        'i[style*="8K_xjKZJOdC.png"]'
    ]
    
    for selector in selectores_boton:
        try:
            elemento = publicacion.locator(selector)
            if await elemento.count() > 0:
                if 'span[data-ad-rendering-role="comment_button"]' in selector:
                    texto = await elemento.first.text_content()
                    if texto and "comentar" in texto.lower():
                        return elemento.first.locator('..').locator('..').locator('..')
                elif 'i[style*="8K_xjKZJOdC.png"]' in selector:
                    return elemento.first.locator('..').locator('..').locator('..')
                else:
                    return elemento.first
        except:
            continue
    
    return None

async def extraer_descripcion_completa_de_modal(modal):
    selectores_principales = [
        "div[data-testid='post_message']",
        "div[data-ad-preview='message']",
        "div[data-testid='post_message'] div[dir='auto']",
        "div[data-ad-preview='message'] div[dir='auto']"
    ]
    
    for selector in selectores_principales:
        elementos = modal.locator(selector)
        if await elementos.count() > 0:
            textos = await elementos.all_text_contents()
            textos_filtrados = [t.strip() for t in textos if t.strip() and len(t.split()) > 3]
            if textos_filtrados:
                texto_unido = ' '.join(textos_filtrados)
                if len(texto_unido) > 20:
                    return normalizar_texto(texto_unido)
    
    elementos_dir = modal.locator("div[dir='auto']")
    if await elementos_dir.count() > 0:
        textos = await elementos_dir.all_text_contents()
        textos_filtrados = []
        for texto in textos:
            if (len(texto.split()) > 3 and 
                not re.search(r'hace \d+ minutos?|hace \d+ horas?|hace \d+ dias?|ago|minutes?|hours?|days?', texto, re.IGNORECASE)):
                textos_filtrados.append(texto)
        
        if textos_filtrados:
            texto_mas_largo = max(textos_filtrados, key=len)
            return normalizar_texto(texto_mas_largo)
    
    return None

async def extraer_comentarios_del_modal(modal, limite=10):
    comentarios_validos = []
    
    await scroll_modal_comentarios(modal, 2)
    
    selectores_comentarios = [
        "div[role='article']",
        "div[data-testid='UFI2Comment/body']",
        "div[data-testid='comment']",
        "div[aria-label*='comment' i]",
        "div[aria-label*='comentario' i]"
    ]
    
    elementos_comentarios = None
    
    for selector in selectores_comentarios:
        elementos = modal.locator(selector)
        if await elementos.count() > 0:
            elementos_comentarios = elementos
            break
    
    if elementos_comentarios:
        cantidad_elementos = await elementos_comentarios.count()
        comentarios_procesados = 0
        
        for i in range(min(cantidad_elementos, limite * 2)):
            if comentarios_procesados >= limite:
                break
                
            elemento = elementos_comentarios.nth(i)
            
            try:
                texto_completo = await elemento.text_content()
                
                if not texto_completo:
                    continue
                
                comentario_limpio = limpiar_comentario_facebook(texto_completo)
                
                if not es_comentario_valido(comentario_limpio):
                    continue
                
                # Evitar duplicados
                if comentario_limpio in comentarios_validos:
                    continue
                
                # Truncar comentarios muy largos
                if len(comentario_limpio) > 200:
                    comentario_limpio = comentario_limpio[:200].strip()
                
                comentarios_validos.append(comentario_limpio)
                comentarios_procesados += 1
                
            except Exception as e:
                continue
    
    return comentarios_validos

async def scroll_modal_comentarios(modal, veces=2):
    try:
        for i in range(veces):
            await modal.evaluate("(element) => element.scrollTop = element.scrollHeight")
            await modal.page.wait_for_timeout(500)
    except:
        pass

async def scroll_hasta_cargar_nuevas_publicaciones(page, publicaciones_actuales):
    max_intentos = 5
    scroll_intensivo = 0
    
    while scroll_intensivo < max_intentos:
        scroll_anterior = await page.evaluate("window.pageYOffset")
        
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1000)
        
        scroll_actual = await page.evaluate("window.pageYOffset")
        
        nuevas_publicaciones = page.locator('div[role="feed"] > div[data-virtualized="false"]')
        cantidad_nueva = await nuevas_publicaciones.count()
        
        if cantidad_nueva > publicaciones_actuales:
            return cantidad_nueva
        
        if scroll_actual == scroll_anterior:
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(1000)
        
        scroll_intensivo += 1
    
    return await nuevas_publicaciones.count()

def generar_json_resultados(results, query):
    """Genera el archivo JSON con los resultados del scraping"""
    try:
        # Formatear los resultados según el formato solicitado
        json_data = []
        
        for result in results:
            json_entry = {
                "url": result.get("url", ""),
                "text": result.get("text", "")
            }
            json_data.append(json_entry)
        
        # Crear nombre del archivo con timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"facebook_scraping_{query.replace(' ', '_')}_{timestamp}.json"
        
        # Guardar el archivo JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"JSON generado: {filename} con {len(json_data)} publicaciones")
        return filename
        
    except Exception as e:
        logger.error(f"Error al generar JSON: {str(e)}")
        return None

class FacebookScraper:
    def __init__(self):
        self.logger = logger

    async def scrape_facebook_posts(self, query: str, max_results: int = 10):
        """Función principal de scraping de Facebook"""
        try:
            results = []
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--disable-gpu',
                        '--no-sandbox',
                        '--disable-extensions',
                        '--disable-plugins',
                        '--disable-images',
                        '--disable-javascript-harmony-shipping',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding',
                        '--disable-features=VizDisplayCompositor'
                    ]
                )
                
                context = await browser.new_context(
                    storage_state="facebook_session.json",
                    viewport={'width': 1280, 'height': 720}
                )
                
                page = await context.new_page()
                
                # Bloquear recursos innecesarios
                await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())

                await page.goto("https://www.facebook.com/")
                await page.wait_for_timeout(2000)

                search_url = f"https://www.facebook.com/search/top?q={query.replace(' ', '%20')}"
                await page.goto(search_url)
                await page.wait_for_timeout(3000)

                await page.get_by_role("link", name="Publicaciones").click()
                await page.wait_for_timeout(3000)

                publicaciones_procesadas = 0
                indice_actual = 0
                
                while publicaciones_procesadas < max_results:
                    publicaciones = page.locator('div[role="feed"] > div[data-virtualized="false"]')
                    cantidad_actual = await publicaciones.count()
                    
                    if cantidad_actual <= indice_actual:
                        nueva_cantidad = await scroll_hasta_cargar_nuevas_publicaciones(page, cantidad_actual)
                        if nueva_cantidad <= cantidad_actual:
                            break  # No hay más publicaciones
                        cantidad_actual = nueva_cantidad
                    
                    if indice_actual >= cantidad_actual:
                        break
                    
                    publicacion = publicaciones.nth(indice_actual)
                    
                    try:
                        await publicacion.scroll_into_view_if_needed()
                        await page.wait_for_timeout(200)
                        
                        if await es_video_o_short(publicacion):
                            self.logger.info(f"[{indice_actual + 1}] Video/short - OMITIDA")
                            indice_actual += 1
                            continue
                        
                        if not await tiene_descripcion_suficiente(publicacion):
                            self.logger.info(f"[{indice_actual + 1}] Descripción insuficiente - OMITIDA")
                            indice_actual += 1
                            continue
                        
                        boton_comentar = await buscar_boton_comentar(publicacion)
                        
                        if not boton_comentar:
                            self.logger.info(f"[{indice_actual + 1}] Sin botón comentar - OMITIDA")
                            indice_actual += 1
                            continue
                        
                        try:
                            await boton_comentar.wait_for(state="visible", timeout=3000)
                            await boton_comentar.click()
                            self.logger.info(f"[{indice_actual + 1}] Modal abierto - PROCESANDO")
                        except Exception as e:
                            self.logger.error(f"[{indice_actual + 1}] Error al abrir modal - OMITIDA")
                            indice_actual += 1
                            continue
                        
                        await page.wait_for_timeout(2000)
                        
                        try:
                            modal = page.locator("div[role='dialog']")
                            await modal.wait_for(timeout=5000)
                        except:
                            self.logger.error(f"[{indice_actual + 1}] Modal no cargó - ERROR")
                            await page.keyboard.press("Escape")
                            indice_actual += 1
                            continue
                        
                        descripcion = await extraer_descripcion_completa_de_modal(modal)
                        
                        if descripcion:
                            comentarios = await extraer_comentarios_del_modal(modal, limite=10)
                            
                            # Combinar descripción y comentarios
                            contenido_completo = descripcion
                            if comentarios:
                                contenido_completo += ", " + ", ".join(comentarios)
                            
                            contenido_completo = normalizar_texto(contenido_completo)
                            
                            result = {
                                "url": search_url,
                                "text": contenido_completo,
                                "user": "facebook_user",
                                "created_at": datetime.now().isoformat(),
                                "retweet_count": 0,
                                "favorite_count": 0,
                                "comment_count": len(comentarios)
                            }
                            
                            results.append(result)
                            publicaciones_procesadas += 1
                            
                            self.logger.info(f"[{indice_actual + 1}] GUARDADA: {len(contenido_completo.split())} palabras, {len(comentarios)} comentarios")
                        else:
                            self.logger.info(f"[{indice_actual + 1}] Sin descripción - OMITIDA")
                        
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(200)
                        
                    except Exception as e:
                        self.logger.error(f"[{indice_actual + 1}] Error: {str(e)}")
                        try:
                            await page.keyboard.press("Escape")
                            await page.wait_for_timeout(200)
                        except:
                            pass
                    
                    indice_actual += 1
                
                await browser.close()
                
            # Generar el archivo JSON con los resultados
            if results:
                json_filename = generar_json_resultados(results, query)
                if json_filename:
                    self.logger.info(f"Scraping completado. Resultados guardados en: {json_filename}")
                else:
                    self.logger.error("Error al generar el archivo JSON")
            else:
                self.logger.warning("No se encontraron resultados para procesar")
                
            return results
                
        except Exception as e:
            self.logger.error(f"Error en scraping de Facebook: {str(e)}")
            raise

# Función wrapper para usar en la API principal
async def scrape_facebook(query: str, max_results: int = 10, max_workers: int = 3):
    """Wrapper function to match the interface of other scrapers"""
    scraper = FacebookScraper()
    
    # Ejecutar el scraping asíncrono
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        results = await scraper.scrape_facebook_posts(query, max_results)
        return results
    finally:
        loop.close()