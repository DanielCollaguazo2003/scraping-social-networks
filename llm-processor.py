from transformers import pipeline
import torch

class AnalizadorTexto:
    def __init__(self):
        """
        Inicializa los modelos de clasificación y análisis de sentimientos
        """
        
        self.clasificador = pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=0 if torch.cuda.is_available() else -1
        )
        
        self.analizador_sentimientos = pipeline(
            "sentiment-analysis",
            model="nlptown/bert-base-multilingual-uncased-sentiment",
            device=0 if torch.cuda.is_available() else -1
        )
        
        self.categorias = [
            "Turismo",
            "Gastronomía",
            "Seguridad y Delincuencia", 
            "Eventos",
            "Salud"
        ]
    
    def analizar_sentimiento(self, texto):
        """
        Analiza el sentimiento del texto (positivo/negativo)
        
        Args:
            texto (str): Texto a analizar
            
        Returns:
            dict: Diccionario con el sentimiento y la confianza
        """
        try:
            resultado = self.analizador_sentimientos(texto)
            
            if isinstance(resultado, list):
                resultado = resultado[0]
            
            label = resultado['label']
            score = resultado['score']
            
            if 'POSITIVE' in label.upper() or '4' in label or '5' in label:
                sentimiento = "Positivo"
            elif 'NEGATIVE' in label.upper() or '1' in label or '2' in label:
                sentimiento = "Negativo"
            else:
                sentimiento = "Positivo" if score > 0.5 else "Negativo"
            
            return {
                "sentimiento": sentimiento,
                "confianza": round(score, 4),
                "label_original": label
            }
            
        except Exception as e:
            print(f"Error en análisis de sentimientos: {e}")
            return {
                "sentimiento": "No determinado",
                "confianza": 0.0,
                "label_original": "Error"
            }
    
    def clasificar_categoria(self, texto):
        """
        Clasifica el texto en una de las categorías predefinidas
        
        Args:
            texto (str): Texto a clasificar
            
        Returns:
            dict: Diccionario con la categoría y las puntuaciones
        """
        try:
            resultado = self.clasificador(texto, self.categorias)
            
            return {
                "categoria_principal": resultado['labels'][0],
                "confianza": round(resultado['scores'][0], 4),
                "todas_las_categorias": [
                    {
                        "categoria": label,
                        "puntuacion": round(score, 4)
                    }
                    for label, score in zip(resultado['labels'], resultado['scores'])
                ]
            }
            
        except Exception as e:
            print(f"Error en clasificación: {e}")
            return {
                "categoria_principal": "No determinada",
                "confianza": 0.0,
                "todas_las_categorias": []
            }
    
    def analizar_texto_completo(self, texto):
        """
        Función principal que combina análisis de sentimientos y clasificación
        
        Args:
            texto (str): Texto a analizar
            
        Returns:
            dict: Análisis completo del texto
        """
        if not texto or not isinstance(texto, str):
            return {
                "error": "El texto debe ser una cadena no vacía",
                "texto": texto
            }
        
        # Realizar ambos análisis
        sentimiento = self.analizar_sentimiento(texto)
        clasificacion = self.clasificar_categoria(texto)
        
        return {
            "texto": texto,
            "sentimiento": sentimiento,
            "clasificacion": clasificacion,
            "resumen": f"Texto clasificado como '{clasificacion['categoria_principal']}' "
                      f"con sentimiento '{sentimiento['sentimiento']}' "
                      f"(confianza: {clasificacion['confianza']})"
        }

def analizar_texto(texto):
    """
    Función independiente para análisis rápido de texto
    
    Args:
        texto (str): Texto a analizar
        
    Returns:
        dict: Resultado del análisis
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