from transformers import pipeline
import torch

class AnalizadorTexto:
    def __init__(self):
        """
        Inicializa los modelos de clasificación y análisis de sentimientos,
        configurando el dispositivo automáticamente (GPU si está disponible).
        """
        device = 0 if torch.cuda.is_available() else -1

        self.clasificador = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=device
        )

        self.analizador_sentimientos = pipeline(
            "sentiment-analysis",
            model="nlptown/bert-base-multilingual-uncased-sentiment",
            device=device
        )

        self.categorias = [
            "Turismo",
            "Gastronomía",
            "Seguridad y Delincuencia",
            "Eventos",
            "Salud"
        ]
        
    

    def analizar_sentimiento(self, texto: str) -> dict:
        try:
            resultado = self.analizador_sentimientos(texto)
            if isinstance(resultado, list):
                resultado = resultado[0]

            label = resultado.get('label', '')
            score = resultado.get('score', 0.0)

            # 🟡 Traduce "5 stars" a "positive", etc. (lo que espera tu modelo)
            if "star" in label.lower():
                rating = int(label[0])
                if rating >= 4:
                    simplified_label = "positive"
                    sentimiento = "Positivo"
                elif rating <= 2:
                    simplified_label = "negative"
                    sentimiento = "Negativo"
                else:
                    simplified_label = "neutral"
                    sentimiento = "Neutro"
            else:
                label_upper = label.upper()
                if "POSITIVE" in label_upper:
                    simplified_label = "positive"
                    sentimiento = "Positivo"
                elif "NEGATIVE" in label_upper:
                    simplified_label = "negative"
                    sentimiento = "Negativo"
                else:
                    simplified_label = "neutral"
                    sentimiento = "Neutro"

            return {
                "label": simplified_label,  # ⚠️ ¡Ahora compatible con el Enum!
                "score": score,
                "confidence": round(score, 4),
                "sentimiento": sentimiento
            }

        except Exception as e:
            print(f"Error en análisis de sentimientos: {e}")
            return {
                "label": None,
                "score": 0.0,
                "confidence": 0.0,
                "sentimiento": "No determinado"
            }



    def clasificar_categoria(self, texto: str) -> dict:
        """
        Clasifica el texto en una de las categorías predefinidas.

        Args:
            texto (str): Texto a clasificar.

        Returns:
            dict: Diccionario con:
                - categoria_principal (str)
                - confianza (float)
                - todas_las_categorias (list de dicts con 'categoria' y 'puntuacion')
        """
        try:
            resultado = self.clasificador(texto, self.categorias)

            labels = resultado.get('labels', [])
            scores = resultado.get('scores', [])

            if not labels or not scores:
                raise ValueError("Resultado del clasificador vacío")

            return {
                "categoria_principal": labels[0],
                "confianza": round(scores[0], 4),
                "todas_las_categorias": [
                    {"categoria": lbl, "puntuacion": round(scr, 4)}
                    for lbl, scr in zip(labels, scores)
                ]
            }
        except Exception as e:
            print(f"Error en clasificación: {e}")
            return {
                "categoria_principal": "No determinada",
                "confianza": 0.0,
                "todas_las_categorias": []
            }

    def analizar_texto_completo(self, texto: str) -> dict:
        """
        Realiza análisis completo: sentimiento + categoría.

        Args:
            texto (str): Texto a analizar.

        Returns:
            dict: Resultado combinado con las claves:
                - texto
                - sentimiento (dict)
                - clasificacion (dict)
                - resumen (str)
        """
        if not texto or not isinstance(texto, str):
            return {
                "error": "El texto debe ser una cadena no vacía",
                "texto": texto
            }

        sentimiento = self.analizar_sentimiento(texto)
        clasificacion = self.clasificar_categoria(texto)

        resumen = (
            f"Texto clasificado como '{clasificacion.get('categoria_principal', 'No determinada')}' "
            f"con sentimiento '{sentimiento.get('sentimiento', 'No determinado')}' "
            f"(confianza: {clasificacion.get('confianza', 0.0)})"
        )

        return {
            "texto": texto,
            "sentimiento": sentimiento,
            "clasificacion": clasificacion,
            "resumen": resumen
        }


def analizar_texto(texto: str) -> dict:
    """
    Función auxiliar para análisis rápido.

    Args:
        texto (str): Texto a analizar.

    Returns:
        dict: Resultado del análisis completo.
    """
    analizador = AnalizadorTexto()
    return analizador.analizar_texto_completo(texto)


if __name__ == "__main__":
    analizador = AnalizadorTexto()

    textos_ejemplo = [
        "El restaurante tenía una comida deliciosa y el servicio fue excelente",
        "Me robaron la cartera en el centro de la ciudad, muy inseguro",
        "El concierto de rock estuvo increíble, la banda tocó genial",
        "El hospital tiene muy buena atención médica y doctores capacitados",
        "Las playas de esta ciudad son hermosas, perfectas para vacacionar"
    ]

    print("=== ANÁLISIS DE TEXTOS ===\n")

    for i, texto in enumerate(textos_ejemplo, 1):
        print(f"Ejemplo {i}:")
        print(f"Texto: {texto}")

        resultado = analizador.analizar_texto_completo(texto)

        print(f"Categoría: {resultado['clasificacion']['categoria_principal']}")
        print(f"Sentimiento: {resultado['sentimiento']['sentimiento']}")
        print(f"Confianza categoría: {resultado['clasificacion']['confianza']}")
        print(f"Confianza sentimiento: {resultado['sentimiento']['confianza']}")
        print("-" * 50)

    print("\n=== USANDO FUNCIÓN INDEPENDIENTE ===")
    texto_prueba = "La nueva cafetería tiene un ambiente acogedor pero los precios son muy altos"
    resultado = analizar_texto(texto_prueba)
    print(f"Texto: {resultado['texto']}")
    print(f"Resumen: {resultado['resumen']}")
