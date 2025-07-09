import os
import re
import unicodedata
import csv

# Palabras clave turísticas
KEYWORDS_TURISMO = [
    "tour", "paseo", "guía", "viaje", "turismo", "excursión",
    "precio", "costo", "horario", "información", "visita", "lugar",
    "sitio", "hermoso", "bonito", "recomiendo", "destino", "agencia",
    "hotel", "hospedaje", "transporte", "ruta", "conocer", "termales", "playa", "montaña"
]

# Palabras ofensivas
PALABRAS_FEAS = [
    "mierda", "puta", "puto", "maldito", "idiota", "pendejo", "coño", "culero",
    "estúpido", "imbécil", "marica", "hijueputa", "cabron", "hdp", "perra"
]

# Expresiones regulares
REGEX_EMOJIS = re.compile("["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"
    "\U0001F680-\U0001F6FF"
    "\U0001F1E0-\U0001F1FF"
    "\U00002500-\U00002BEF"
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+", flags=re.UNICODE)

REGEX_URL = re.compile(r'https?://\S+|www\.\S+')
REGEX_MENCION = re.compile(r'@\w+')

def limpiar_texto(texto: str) -> str:
    texto = REGEX_EMOJIS.sub('', texto)
    texto = REGEX_URL.sub('', texto)
    texto = REGEX_MENCION.sub('', texto)
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    palabras = texto.split()
    limpio = [p for p in palabras if p.lower() not in PALABRAS_FEAS]
    return " ".join(limpio)

def detectar_keywords(texto_limpio: str):
    palabras = texto_limpio.lower().split()
    return sorted(set(p for p in palabras if p in KEYWORDS_TURISMO))

def limpiar_archivo(origen_path, destino_path, csv_writer):
    with open(origen_path, "r", encoding="utf-8") as f:
        lineas = f.readlines()

    nuevas_lineas = []
    usuario = "Usuario desconocido"

    for linea in lineas:
        if linea.startswith("Usuario:"):
            usuario = linea.replace("Usuario:", "").strip()
            nuevas_lineas.append(linea)
        elif linea.startswith("Texto:"):
            original = linea.replace("Texto:", "").strip()
            limpio = limpiar_texto(original)
            nuevas_lineas.append(f"Texto: {limpio}\n")

            # Detectar keywords turísticas
            keywords = detectar_keywords(limpio)
            if keywords:
                csv_writer.writerow({
                    'usuario': usuario,
                    'comentario': limpio,
                    'keywords_detectadas': ", ".join(keywords)
                })
        else:
            nuevas_lineas.append(linea)

    with open(destino_path, "w", encoding="utf-8") as f:
        f.writelines(nuevas_lineas)

def procesar_todos():
    carpeta_origen = "comentarios"
    carpeta_destino = "limpieza"
    if not os.path.exists(carpeta_destino):
        os.makedirs(carpeta_destino)

    with open("turismo_keywords.csv", "w", newline='', encoding="utf-8") as csvfile:
        fieldnames = ["usuario", "comentario", "keywords_detectadas"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for archivo in os.listdir(carpeta_origen):
            if archivo.endswith(".txt") and "video_" in archivo:
                origen = os.path.join(carpeta_origen, archivo)
                destino = os.path.join(carpeta_destino, archivo)
                print(f"🧼 Limpiando y extrayendo de: {archivo}")
                limpiar_archivo(origen, destino, writer)

if __name__ == "__main__":
    procesar_todos()
    print("✅ Limpieza completada. Archivos en 'limpieza' y CSV generado como 'turismo_keywords.csv'")
