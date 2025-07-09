import os
import re
import unicodedata

# Lista simple de palabras ofensivas en español (puedes expandirla)
PALABRAS_FEAS = [
    "mierda", "puta", "puto", "maldito", "idiota", "pendejo", "coño", "culero",
    "estúpido", "imbécil", "marica", "hijueputa", "cabron", "hdp", "perra"
]

# Expresiones regulares
REGEX_EMOJIS = re.compile("["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002500-\U00002BEF"  # chinese characters
    "\U00002702-\U000027B0"
    "\U000024C2-\U0001F251"
    "]+", flags=re.UNICODE)

REGEX_URL = re.compile(r'https?://\S+|www\.\S+')
REGEX_MENCION = re.compile(r'@\w+')

def limpiar_texto(texto: str) -> str:
    """Limpia emojis, menciones, URLs y palabras ofensivas."""
    texto = REGEX_EMOJIS.sub('', texto)
    texto = REGEX_URL.sub('', texto)
    texto = REGEX_MENCION.sub('', texto)

    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")

    palabras = texto.split()
    limpio = [p for p in palabras if p.lower() not in PALABRAS_FEAS]
    return " ".join(limpio)

def limpiar_archivo(origen_path, destino_path):
    with open(origen_path, "r", encoding="utf-8") as f:
        lineas = f.readlines()

    nuevas_lineas = []
    for linea in lineas:
        if linea.startswith("Texto:"):
            original = linea.replace("Texto:", "").strip()
            limpio = limpiar_texto(original)
            nuevas_lineas.append(f"Texto: {limpio}\n")
        else:
            nuevas_lineas.append(linea)

    with open(destino_path, "w", encoding="utf-8") as f:
        f.writelines(nuevas_lineas)

def procesar_todos():
    carpeta_origen = "comentarios"
    carpeta_destino = "limpieza"

    if not os.path.exists(carpeta_destino):
        os.makedirs(carpeta_destino)

    for archivo in os.listdir(carpeta_origen):
        if archivo.endswith(".txt") and "video_" in archivo:
            origen = os.path.join(carpeta_origen, archivo)
            destino = os.path.join(carpeta_destino, archivo)
            print(f"🧹 Limpiando {archivo}...")
            limpiar_archivo(origen, destino)

if __name__ == "__main__":
    procesar_todos()
    print("✅ Limpieza completada. Archivos guardados en carpeta 'limpieza'")
