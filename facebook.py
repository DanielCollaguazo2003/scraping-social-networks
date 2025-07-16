import asyncio
import json
import re
import os
import unicodedata
from datetime import datetime
from playwright.async_api import async_playwright

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

def cargar_datos_existentes(archivo):
    if os.path.exists(archivo):
        try:
            with open(archivo, 'r', encoding='utf-8') as f:
                datos = json.load(f)
                return datos if isinstance(datos, list) else []
        except (json.JSONDecodeError, IOError):
            return []
    return []

def guardar_publicacion_inmediata(archivo, nueva_publicacion):
    datos_existentes = cargar_datos_existentes(archivo)
    datos_existentes.append(nueva_publicacion)
    
    try:
        with open(archivo, 'w', encoding='utf-8') as f:
            json.dump(datos_existentes, f, ensure_ascii=False, indent=2)
        return True
    except IOError:
        return False

def obtener_descripciones_existentes(archivo):
    datos_existentes = cargar_datos_existentes(archivo)
    return set(item.get('content', '') for item in datos_existentes)

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

async def extraer_comentarios_del_modal(modal, limite=20):
    comentarios_validos = []
    
    await scroll_modal_comentarios(modal, 2)  # Reducido de 3 a 2
    
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
        
        for i in range(min(cantidad_elementos, limite * 2)):  # Reducido de limite * 3 a limite * 2
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

async def scroll_modal_comentarios(modal, veces=2):  # Reducido de 3 a 2
    try:
        for i in range(veces):
            await modal.evaluate("(element) => element.scrollTop = element.scrollHeight")
            await modal.page.wait_for_timeout(800)  # Reducido de 1500 a 800
    except:
        pass

async def scroll_hasta_cargar_nuevas_publicaciones(page, publicaciones_actuales):
    max_intentos = 8  # Reducido de 10 a 8
    scroll_intensivo = 0
    
    while scroll_intensivo < max_intentos:
        scroll_anterior = await page.evaluate("window.pageYOffset")
        
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(1500)  # Reducido de 3000 a 1500
        
        scroll_actual = await page.evaluate("window.pageYOffset")
        
        nuevas_publicaciones = page.locator('div[role="feed"] > div[data-virtualized="false"]')
        cantidad_nueva = await nuevas_publicaciones.count()
        
        if cantidad_nueva > publicaciones_actuales:
            return cantidad_nueva
        
        if scroll_actual == scroll_anterior:
            await page.evaluate("window.scrollBy(0, 1000)")
            await page.wait_for_timeout(1000)  # Reducido de 2000 a 1000
        
        scroll_intensivo += 1
    
    return await nuevas_publicaciones.count()

async def main():
    # Solicitar parámetro de búsqueda
    print("=== FACEBOOK SCRAPER OPTIMIZADO ===")
    print("Ingresa el término de búsqueda:")
    query = input("> ").strip()
    
    if not query:
        print("Error: Debe ingresar un término de búsqueda válido")
        return
    
    print(f"Iniciando scraping para: '{query}'")
    
    ARCHIVO_SALIDA = f"contenido_{query.replace(' ', '_')}.json"
    DELAY_ENTRE_SOLICITUDES = 1  # Reducido de 3 a 1
    
    async with async_playwright() as p:
        # Configuración optimizada para velocidad
        browser = await p.chromium.launch(
            headless=True,  # Sin interfaz gráfica
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-sandbox',
                '--disable-extensions',
                '--disable-plugins',
                '--disable-images',  # No cargar imágenes para mayor velocidad
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
        
        # Bloquear recursos innecesarios para mayor velocidad
        await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())

        await page.goto("https://www.facebook.com/")
        await page.wait_for_timeout(2000)  # Reducido de 3000 a 2000

        search_url = f"https://www.facebook.com/search/top?q={query.replace(' ', '%20')}"
        await page.goto(search_url)
        await page.wait_for_timeout(3000)  # Reducido de 5000 a 3000

        await page.get_by_role("link", name="Publicaciones").click()
        await page.wait_for_timeout(3000)  # Reducido de 5000 a 3000

        descripciones_existentes = obtener_descripciones_existentes(ARCHIVO_SALIDA)
        
        print(f"Datos existentes: {len(descripciones_existentes)} publicaciones")
        print(f"Archivo de salida: {ARCHIVO_SALIDA}")
        print("Iniciando procesamiento...")

        publicaciones_procesadas = 0
        indice_actual = 0
        
        try:
            while True:
                publicaciones = page.locator('div[role="feed"] > div[data-virtualized="false"]')
                cantidad_actual = await publicaciones.count()
                
                if cantidad_actual <= indice_actual:
                    nueva_cantidad = await scroll_hasta_cargar_nuevas_publicaciones(page, cantidad_actual)
                    if nueva_cantidad <= cantidad_actual:
                        await page.wait_for_timeout(2000)  # Reducido de 5000 a 2000
                        continue
                    cantidad_actual = nueva_cantidad
                
                while indice_actual < cantidad_actual:
                    publicacion = publicaciones.nth(indice_actual)
                    
                    try:
                        await publicacion.scroll_into_view_if_needed()
                        await page.wait_for_timeout(200)  # Reducido de 500 a 200
                        
                        if await es_video_o_short(publicacion):
                            print(f"[{indice_actual + 1}] Video/short - OMITIDA")
                            indice_actual += 1
                            continue
                        
                        if not await tiene_descripcion_suficiente(publicacion):
                            print(f"[{indice_actual + 1}] Descripción insuficiente - OMITIDA")
                            indice_actual += 1
                            continue
                        
                        boton_comentar = await buscar_boton_comentar(publicacion)
                        
                        if not boton_comentar:
                            print(f"[{indice_actual + 1}] Sin botón comentar - OMITIDA")
                            indice_actual += 1
                            continue
                        
                        try:
                            await boton_comentar.wait_for(state="visible", timeout=3000)  # Reducido de 5000 a 3000
                            await boton_comentar.click()
                            print(f"[{indice_actual + 1}] Modal abierto - PROCESANDO")
                        except Exception as e:
                            print(f"[{indice_actual + 1}] Error al abrir modal - OMITIDA")
                            indice_actual += 1
                            continue
                        
                        await page.wait_for_timeout(2000)  # Reducido de 3000 a 2000
                        
                        try:
                            modal = page.locator("div[role='dialog']")
                            await modal.wait_for(timeout=5000)  # Reducido de 8000 a 5000
                        except:
                            print(f"[{indice_actual + 1}] Modal no cargó - ERROR")
                            await page.keyboard.press("Escape")
                            indice_actual += 1
                            continue
                        
                        descripcion = await extraer_descripcion_completa_de_modal(modal)
                        
                        if descripcion:
                            comentarios = await extraer_comentarios_del_modal(modal, limite=15)  # Reducido de 20 a 15
                            
                            # Combinar descripción y comentarios
                            contenido_completo = descripcion
                            if comentarios:
                                contenido_completo += ", " + ", ".join(comentarios)
                            
                            contenido_completo = normalizar_texto(contenido_completo)
                            
                            # Verificar duplicados
                            if contenido_completo not in descripciones_existentes:
                                resultado = {
                                    "url": search_url,
                                    "content": contenido_completo,
                                }
                                
                                if guardar_publicacion_inmediata(ARCHIVO_SALIDA, resultado):
                                    publicaciones_procesadas += 1
                                    descripciones_existentes.add(contenido_completo)
                                    print(f"[{indice_actual + 1}] GUARDADA: {len(contenido_completo.split())} palabras, {len(comentarios)} comentarios")
                            else:
                                print(f"[{indice_actual + 1}] Duplicado - OMITIDA")
                        else:
                            print(f"[{indice_actual + 1}] Sin descripción - OMITIDA")
                        
                        await page.keyboard.press("Escape")
                        await page.wait_for_timeout(200)  # Reducido de 500 a 200
                        await page.wait_for_timeout(DELAY_ENTRE_SOLICITUDES * 1000)
                        
                    except Exception as e:
                        print(f"[{indice_actual + 1}] Error: {str(e)}")
                        try:
                            await page.keyboard.press("Escape")
                            await page.wait_for_timeout(200)
                        except:
                            pass
                    
                    indice_actual += 1
                
                if publicaciones_procesadas % 10 == 0 and publicaciones_procesadas > 0:  # Reducido de 20 a 10
                    total_datos = len(cargar_datos_existentes(ARCHIVO_SALIDA))
                    print(f"PROGRESO: {publicaciones_procesadas} procesadas | {total_datos} totales en archivo")
                
        except KeyboardInterrupt:
            print(f"\nDetenido por el usuario")
        except Exception as e:
            print(f"Error inesperado: {str(e)}")
        finally:
            try:
                await browser.close()
            except:
                pass
            
            total_final = len(cargar_datos_existentes(ARCHIVO_SALIDA))
            print(f"\n=== RESUMEN FINAL ===")
            print(f"Término de búsqueda: {query}")
            print(f"Total guardado: {total_final} publicaciones")
            print(f"Archivo: {ARCHIVO_SALIDA}")

if __name__ == "__main__":
    asyncio.run(main())