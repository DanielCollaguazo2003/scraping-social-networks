from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import uuid
from datetime import datetime
from enum import Enum
import json
import openai
import os
from dotenv import load_dotenv
from analizador_texto import AnalizadorTexto

# Importar módulos de scraping
from x import scrape
from tiktok_scraping import TikTokScraper
from facebook import scrape_facebook  # Importar la función de Facebook

from pydantic import BaseModel
from typing import Optional, Dict

from typing import Optional, Dict, Any

class PostData(BaseModel):
    platform: str
    url: str
    content: Optional[str] = None
    user: Optional[str] = None
    created_at: Optional[str] = None
    retweet_count: Optional[int] = 0
    favorite_count: Optional[int] = 0
    sentiment: Optional[Dict[str, Any]] = None  # Lo dejas flexible para evitar error
    error: Optional[str] = None



load_dotenv()
app = FastAPI(title="Multi-Platform Social Media Search API", version="3.0.0")

from fastapi.middleware.cors import CORSMiddleware


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # o limitar a localhost
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# WebSocket Manager
class ConnectionManager:
    def _init_(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, task_id: str):
        await websocket.accept()
        self.active_connections[task_id] = websocket

    def disconnect(self, task_id: str):
        if task_id in self.active_connections:
            del self.active_connections[task_id]

    async def send_progress(self, task_id: str, data: dict):
        if task_id in self.active_connections:
            websocket = self.active_connections[task_id]
            if websocket.client_state == WebSocketState.CONNECTED:
                try:
                    await websocket.send_json(data)
                except:
                    self.disconnect(task_id)

manager = ConnectionManager()

# Enums
class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"

# Models
class SearchRequest(BaseModel):
    query: str
    max_results: Optional[int] = 15
    platforms: Optional[List[str]] = ["twitter", "tiktok", "facebook"]
    analyze_sentiment: Optional[bool] = True

class ReportRequest(BaseModel):
    task_id: str
    report_type: Optional[str] = "summary"
    language: Optional[str] = "es"

class SentimentAnalysis(BaseModel):
    label: SentimentLabel
    score: float
    confidence: float

class PostData(BaseModel):
    platform: str
    url: str
    content: Optional[str] = None
    user: Optional[str] = None
    created_at: Optional[str] = None
    retweet_count: Optional[int] = 0
    favorite_count: Optional[int] = 0
    likes: Optional[int] = 0
    comments_count: Optional[int] = 0
    sentiment: Optional[SentimentAnalysis] = None
    keywords: Optional[List[str]] = None
    error: Optional[str] = None

class TaskInfo(BaseModel):
    task_id: str
    status: TaskStatus
    query: str
    platforms: List[str]
    progress: Dict[str, Any]
    results: Optional[List[PostData]] = None
    platform_results: Optional[Dict[str, List[PostData]]] = None
    total: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    sentiment_summary: Optional[Dict[str, Any]] = None
    gpt_report: Optional[str] = None 

# Storage
tasks_storage: Dict[str, TaskInfo] = {}

class ProgressTracker:
    def _init_(self, task_id: str):
        self.task_id = task_id
        self.platform_progress = {}
    
    async def update_progress(self, step: str, completed: int, total: int, platform: str = None):
        if platform:
            self.platform_progress[platform] = {"step": step, "completed": completed, "total": total}
        
        if self.task_id in tasks_storage:
            percentage = (completed / total * 100) if total > 0 else 0
            progress_data = {
                "current_step": step,
                "percentage": percentage,
                "platform_progress": self.platform_progress
            }
            tasks_storage[self.task_id].progress = progress_data
            
            # Enviar actualización por WebSocket
            await manager.send_progress(self.task_id, {
                "type": "progress_update",
                "task_id": self.task_id,
                "progress": progress_data,
                "platform": platform,
                "timestamp": datetime.now().isoformat()
            })

def calculate_sentiment_summary(results: List[PostData]) -> Dict[str, Any]:
    """Calcula resumen de sentimientos"""
    if not results:
        return {}
    
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    valid_results = 0
    
    for result in results:
        if result.sentiment and result.content:
            sentiment_counts[result.sentiment.label] += 1
            valid_results += 1
    
    if valid_results == 0:
        return {}
    
    return {
        "total_analyzed": valid_results,
        "sentiment_distribution": sentiment_counts,
        "sentiment_percentages": {
            k: round((v / valid_results) * 100, 2) for k, v in sentiment_counts.items()
        },
        "dominant_sentiment": max(sentiment_counts, key=sentiment_counts.get)
    }

def safe_parse_date(raw_date: str) -> Optional[str]:
    """Convierte fecha de Twitter a ISO 8601, si es posible"""
    try:
        # Ejemplo: "Tue Jul 22 20:34:36 +0000 2025"
        dt = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
        return dt.isoformat()
    except Exception as e:
        print(f"[WARN] Error al convertir fecha: {e}")
        return None

async def scrape_twitter_data(query: str, max_results: int, progress_callback, analyze_sentiment: bool = True):
    try:
        await progress_callback("Iniciando Twitter", 0, 100, "twitter")

        results = scrape(query, max_results, max_workers=3)

        post_data = []
        for result in results:
            try:
                content = result.get("text") or ""
                sentiment = None
                if analyze_sentiment and content.strip():
                    analisis_completo = AnalizadorTexto().analizar_texto_completo(content)
                    sentiment = analisis_completo.get("sentimiento")

                post = PostData(
                    platform="twitter",
                    url=result.get("url", ""),
                    content=content,
                    user=result.get("user") or None,
                    created_at=safe_parse_date(result.get("created_at", "")),
                    retweet_count=result.get("retweet_count", 0) or 0,
                    favorite_count=result.get("favorite_count", 0) or 0,
                    sentiment=sentiment,
                    error=result.get("error")
                )
                post_data.append(post)

            except Exception as e:
                print(f"[ERROR] Falló el procesamiento de un resultado: {e}")

        await progress_callback("Twitter completado", 100, 100, "twitter")
        print(f"[DEBUG] Twitter retornó {len(post_data)} resultados")
        return post_data

    except Exception as e:
        await progress_callback("Error en Twitter", 0, 100, "twitter")
        raise

async def scrape_tiktok_data(query: str, max_results: int, progress_callback, analyze_sentiment: bool = True):
    """Scraping de TikTok simplificado con análisis de sentimiento corregido"""
    try:
        await progress_callback("Iniciando TikTok", 0, 100, "tiktok")

        tiktok_scraper = TikTokScraper()
        tiktok_scraper.setup_driver()
        await tiktok_scraper.setup_tiktok_api()

        await progress_callback("Buscando videos", 30, 100, "tiktok")
        videos_data = tiktok_scraper.search_videos(query, max_results)

        if not videos_data:
            await progress_callback("Sin videos", 100, 100, "tiktok")
            return []

        await progress_callback("Extrayendo comentarios", 60, 100, "tiktok")
        all_post_data = []

        analizador = AnalizadorTexto()  # ✅ Instancia del analizador

        for video_data in videos_data:
            try:
                comments = await tiktok_scraper.extract_comments_with_api(video_data['url'], video_data['numero'])

                # Post del video
                sentiment = None
                if analyze_sentiment and video_data.get('descripcion'):
                    resultado = analizador.analizar_texto_completo(video_data['descripcion'])
                    sentimiento_raw = resultado.get("sentimiento")
                    sentiment = SentimentAnalysis(
                        label=sentimiento_raw["label"],
                        score=sentimiento_raw["score"],
                        confidence=sentimiento_raw["confidence"]
                    )

                video_post = PostData(
                    platform="tiktok",
                    url=video_data['url'],
                    content=video_data['descripcion'],
                    user=video_data['usuario'],
                    created_at=datetime.now().isoformat(),
                    sentiment=sentiment,
                    comments_count=len(comments)
                )
                all_post_data.append(video_post)

                # Posts de comentarios
                for comment in comments:
                    comment_sentiment = None
                    if analyze_sentiment and comment.get('texto'):
                        resultado = analizador.analizar_texto_completo(comment['texto'])
                        sentimiento_raw = resultado.get("sentimiento")
                        comment_sentiment = SentimentAnalysis(
                            label=sentimiento_raw["label"],
                            score=sentimiento_raw["score"],
                            confidence=sentimiento_raw["confidence"]
                        )

                    comment_post = PostData(
                        platform="tiktok",
                        url=f"{video_data['url']}#comment_{comment['numero']}",
                        content=comment['texto'],
                        user=comment['autor'],
                        created_at=comment['timestamp'],
                        sentiment=comment_sentiment,
                        likes=comment.get('likes', 0)
                    )
                    all_post_data.append(comment_post)

            except Exception as e:
                print(f"[ERROR] Error procesando video: {e}")
                continue

        tiktok_scraper.close_driver()
        await progress_callback("TikTok completado", 100, 100, "tiktok")
        print(f"[DEBUG] TikTok retornó {len(all_post_data)} resultados")
        return all_post_data

    except Exception as e:
        await progress_callback("Error en TikTok", 0, 100, "tiktok")
        raise

async def scrape_facebook_data(query: str, max_results: int, progress_callback, analyze_sentiment: bool = True):
    """Scraping de Facebook usando la función importada"""
    try:
        await progress_callback("Iniciando Facebook", 0, 100, "facebook")
        
        results = await scrape_facebook(query, max_results, max_workers=3)

        post_data = []

        if not results:
            await progress_callback("Sin resultados de Facebook", 100, 100, "facebook")
            return []

        analizador = AnalizadorTexto()  # ✅ instancia del analizador de texto

        for result in results:
            try:
                sentiment = None
                text = result.get("text", "")
                
                if analyze_sentiment and text:
                    resultado = analizador.analizar_texto_completo(text)
                    sentimiento_raw = resultado.get("sentimiento")
                    sentiment = SentimentAnalysis(
                        label=sentimiento_raw["label"],
                        score=sentimiento_raw["score"],
                        confidence=sentimiento_raw["confidence"]
                    )

                
                post = PostData(
                    platform="facebook",
                    url=result.get("url", ""),
                    content=text,
                    user=result.get("user", "desconocido"),
                    created_at=result.get("created_at", datetime.now().isoformat()),
                    retweet_count=result.get("retweet_count", 0),
                    favorite_count=result.get("favorite_count", 0),
                    comments_count=result.get("comment_count", 0),
                    sentiment=sentiment,
                    error=result.get("error", None)
                )
                post_data.append(post)

            except Exception as post_error:
                print(f"[ERROR] Fallo procesando un post de Facebook: {post_error}")
                continue

        await progress_callback("Facebook completado", 100, 100, "facebook")
        print(f"[DEBUG] Facebook retornó {len(post_data)} resultados")
        return post_data

    except Exception as e:
        await progress_callback("Error en Facebook", 0, 100, "facebook")
        print(f"[ERROR] Scraping general de Facebook falló: {e}")
        return []


async def run_multi_platform_scraping(task_id: str, query: str, max_results: int, platforms: List[str], analyze_sentiment: bool = True):
    """Ejecuta scraping en múltiples plataformas"""
    try:
        tasks_storage[task_id].status = TaskStatus.IN_PROGRESS
        tracker = ProgressTracker(task_id)
        
        # Enviar mensaje de inicio
        await manager.send_progress(task_id, {
            "type": "task_started",
            "task_id": task_id,
            "platforms": platforms,
            "timestamp": datetime.now().isoformat()
        })
        
        async def progress_callback(step: str, completed: int, total: int, platform: str = None):
            await tracker.update_progress(step, completed, total, platform)
        
        # Ejecutar scraping en paralelo
        scraping_tasks = []
        platform_names = []
        
        if "twitter" in platforms:
            scraping_tasks.append(scrape_twitter_data(query, 3, progress_callback, analyze_sentiment))
            platform_names.append("twitter")
        if "tiktok" in platforms:
            scraping_tasks.append(scrape_tiktok_data(query, 3, progress_callback, analyze_sentiment))
            platform_names.append("tiktok")
        if "facebook" in platforms:
            scraping_tasks.append(scrape_facebook_data(query, 3, progress_callback, analyze_sentiment))
            platform_names.append("facebook")
        
        results = await asyncio.gather(*scraping_tasks, return_exceptions=True)
        
        # Procesar resultados - ARREGLADO para no perder datos
        all_results = []
        platform_results = {}
        
        for i, result in enumerate(results):
            platform = platform_names[i]
            if isinstance(result, Exception):
                print(f"Error en {platform}: {str(result)}")  # Debug
                platform_results[platform] = []
                # Enviar error por WebSocket
                await manager.send_progress(task_id, {
                    "type": "platform_error",
                    "task_id": task_id,
                    "platform": platform,
                    "error": str(result),
                    "timestamp": datetime.now().isoformat()
                })
            else:
                platform_results[platform] = result or []  # Asegurar que no sea None
                if result:
                    print(f"[DEBUG] Agregando {len(result)} resultados de {platform}")
                    all_results.extend(result)
                # Enviar completado por WebSocket
                await manager.send_progress(task_id, {
                    "type": "platform_completed",
                    "task_id": task_id,
                    "platform": platform,
                    "results_count": len(result or []),
                    "timestamp": datetime.now().isoformat()
                })
        
        # Actualizar tarea - SIEMPRE, incluso si hay errores parciales
        sentiment_summary = calculate_sentiment_summary(all_results)
        
        tasks_storage[task_id].status = TaskStatus.COMPLETED
        tasks_storage[task_id].results = all_results
        tasks_storage[task_id].platform_results = platform_results
        tasks_storage[task_id].total = len(all_results)
        tasks_storage[task_id].sentiment_summary = sentiment_summary
        tasks_storage[task_id].completed_at = datetime.now()
        
        # Generar el reporte antes de marcar como completado
        reporte = await generar_reporte_chatgpt(tasks_storage[task_id])
        tasks_storage[task_id].gpt_report = reporte

        # Enviar mensaje de finalización (ahora sí, con todo listo)
        await manager.send_progress(task_id, {
            "type": "task_completed",
            "task_id": task_id,
            "total_results": len(all_results),
            "sentiment_summary": sentiment_summary,
            "gpt_report": reporte,  # si quieres enviarlo también por socket
            "timestamp": datetime.now().isoformat()
        })

        
        
    except Exception as e:
        print(f"Error general en scraping: {str(e)}")  # Debug
        tasks_storage[task_id].status = TaskStatus.FAILED
        tasks_storage[task_id].error = str(e)
        tasks_storage[task_id].completed_at = datetime.now()
        
        # Enviar error por WebSocket
        await manager.send_progress(task_id, {
            "type": "task_failed",
            "task_id": task_id,
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        })
        
        
def preparar_datos_para_chatgpt(task_info: TaskInfo) -> str:
    """Genera un reporte completo para ChatGPT a partir de la información de la tarea"""
    lines = []

    # Información general de la tarea
    lines.append(f"🧾 Reporte de Tarea: {task_info.task_id}")
    lines.append(f"🔍 Consulta: {task_info.query}")
    lines.append(f"📡 Plataformas: {', '.join(task_info.platforms)}")
    lines.append(f"📊 Total de resultados: {task_info.results}")
    lines.append(f"📅 Creada: {task_info.created_at}")
    lines.append(f"✅ Completada: {task_info.completed_at}")
    lines.append(f"📌 Estado: {task_info.status.value}")

    # Resumen de sentimientos
    if task_info.sentiment_summary:
        lines.append("\n📈 Resumen de Sentimientos:")
        for k, v in task_info.sentiment_summary.items():
            lines.append(f"  - {k.capitalize()}: {v}")
    
    # Resultados por plataforma
    if task_info.platform_results:
        lines.append("\n🗂 Resultados por Plataforma:")
        for platform, posts in task_info.platform_results.items():
            lines.append(f"\n🔹 {platform}:")
            for post in posts:
                sentiment = post.sentiment.label if post.sentiment else "N/A"
                lines.append(f"  • {post.content or ''} (Sentimiento: {sentiment})")

    elif task_info.results:
        # Resultados sin distinción por plataforma
        lines.append("\n📝 Resultados:")
        for post in task_info.results:
            sentiment = post.sentiment.label if post.sentiment else "N/A"
            lines.append(f"  • [{post.platform}] {post.content or ''} (Sentimiento: {sentiment})")

    return "\n".join(lines)



PROMPT_BASE = """
Actúa como un analista de datos turísticos.

A partir de los siguientes textos extraídos de redes sociales, responde *exclusivamente* en formato JSON (no incluyas explicaciones adicionales ni texto fuera del JSON). El JSON debe incluir las siguientes categorías, cada una con un reporte (resumen de análisis) y los datos estructurados correspondientes:

{
  "eventos_turisticos": {
    "reporte": "", 
    "eventos": [
      {
        "nombre": "",
        "fecha": "",
        "ubicacion": "",
        "descripcion": ""
      }
    ]
  },
  "alertas": {
    "reporte": "", 
    "alertas": [
      {
        "titulo": "",
        "fecha": "",
        "ubicacion": "",
        "nivel": "Alta | Media | Baja",
        "icono": "",
        "explicacion": ""
      }
    ]
  },
  "precios": {
    "reporte": "",
    "comida": "",
    "hospedaje": "",
    "transporte": "",
    "actividades": ""
  },
  "gastronomia": {
    "reporte": "",
    "platos": [
      {
        "nombre": "",
        "descripcion": ""
      }
    ]
  },
  "seguridad": {
    "reporte": "",
    "incidentes": [
      {
        "titulo": "",
        "fecha": "",
        "ubicacion": "",
        "nivel": "Alto | Medio | Bajo",
        "icono": "",
        "reporte": ""
      }
    ]
  },
  "salud": {
    "reporte": "",
    "noticias": [
      {
        "titulo": "",
        "fecha": "",
        "nota": "",
        "nivel": "Alta | Media | Baja",
        "icono": "",
        "reporte": ""
      }
    ]
  },
  "opiniones": {
    "reporte": "",
    "comentarios": [
      {
        "usuario": "",
        "calificacion": 1-5,
        "fecha": "",
        "comentario": ""
      }
    ]
  }
}

Devuelve los campos que apliquen según los textos. Si no hay datos en una categoría, deja "reporte": "Sin datos relevantes encontrados" y el arreglo correspondiente vacío ([]), en caso de haber resultados coloca el repote con datos reales, del analisis de sentimientos con metricas y eso.

Aquí están los textos:
---
{TEXTOS}
"""


import openai

async def generar_reporte_chatgpt(task_info: TaskInfo) -> str:
    contenido = preparar_datos_para_chatgpt(task_info)
    prompt = PROMPT_BASE.replace("{TEXTOS}", contenido)
    print("Prompt para ChatGPT:", prompt)  # Debug

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Eres un experto en análisis social turístico."},
            {"role": "user", "content": prompt}
        ]
    )

    resultado = response.choices[0].message.content
    print(f"[GPT] Reporte generado:\n{resultado}")
    return resultado

 
        

# WebSocket endpoint
@app.websocket("/ws/{task_id}")
async def websocket_endpoint(websocket: WebSocket, task_id: str):
    await manager.connect(websocket, task_id)
    try:
        while True:
            # Mantener la conexión viva
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(task_id)

# ENDPOINTS
@app.post("/search")
async def search(request: SearchRequest, background_tasks: BackgroundTasks):
    """Iniciar búsqueda multi-plataforma"""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="La búsqueda no puede estar vacía")
    
    valid_platforms = ["twitter", "tiktok", "facebook"]
    platforms = [p for p in request.platforms if p in valid_platforms]
    
    if not platforms:
        raise HTTPException(status_code=400, detail=f"Plataformas válidas: {valid_platforms}")
    
    task_id = str(uuid.uuid4())
    
    task_info = TaskInfo(
        task_id=task_id,
        status=TaskStatus.PENDING,
        query=request.query,
        platforms=platforms,
        progress={"current_step": "En cola", "percentage": 0},
        created_at=datetime.now()
    )
    
    tasks_storage[task_id] = task_info
    
    background_tasks.add_task(
        run_multi_platform_scraping, 
        task_id, 
        request.query, 
        request.max_results, 
        platforms,
        request.analyze_sentiment
    )
    
    return {
        "task_id": task_id,
        "status": TaskStatus.PENDING,
        "message": f"Búsqueda iniciada en {len(platforms)} plataformas",
        "platforms": platforms,
        "websocket_url": f"/ws/{task_id}"
    }
    
@app.get("/results/{task_id}")
async def get_results(task_id: str):
    """Obtener resultados de una tarea"""
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    task_info = tasks_storage[task_id]
    
    response_data = {
        "task_id": task_info.task_id,
        "status": task_info.status.value,
        "query": task_info.query,
        "platforms": task_info.platforms,
        "total_results": task_info.total,
        "created_at": task_info.created_at,
        "completed_at": task_info.completed_at
    }
    
    if task_info.status == TaskStatus.COMPLETED:
        response_data.update({
            "results": [serialize_post(result) for result in task_info.results] if task_info.results else [],
            "platform_results": {
                platform: [serialize_post(result) for result in results] 
                for platform, results in (task_info.platform_results or {}).items()
            },
            "sentiment_summary": task_info.sentiment_summary or {},
            "gpt_report": task_info.gpt_report or "No se pudo generar el reporte de IA."
        })
    
    if task_info.error:
        response_data["error"] = task_info.error

    if task_info.status != TaskStatus.COMPLETED:
        response_data["progress"] = task_info.progress
    
    return response_data  # ✅ NECESARIO

@app.get("/progress/{task_id}")
async def get_progress(task_id: str):
    """Obtener progreso de una tarea"""
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    return tasks_storage[task_id]

def serialize_post(post: PostData) -> dict:
    """Convierte un objeto PostData en un diccionario serializable."""
    if post is None:
        return {}
    data = post.dict()
    # Si el campo 'sentiment' es un objeto, conviértelo a dict
    if data.get("sentiment") and hasattr(data["sentiment"], "dict"):
        data["sentiment"] = data["sentiment"].dict()
    return data


    
    # Si hay error, mostrarlo
    if task_info.error:
        response_data["error"] = task_info.error
    
    # Solo mostrar progreso si la tarea no está completada
    if task_info.status != TaskStatus.COMPLETED:
        response_data["progress"] = task_info.progress
    
    return response_data

# También arregla esta parte en run_multi_platform_scraping:

        
@app.get("/tasks")
async def get_tasks():
    """Obtener todas las tareas"""
    return {
        "tasks": [
            {
                "task_id": task.task_id,
                "status": task.status,
                "query": task.query,
                "platforms": task.platforms,
                "total_results": task.total,
                "created_at": task.created_at
            }
            for task in tasks_storage.values()
        ]
    }

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Eliminar una tarea"""
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    # Desconectar WebSocket si existe
    manager.disconnect(task_id)
    del tasks_storage[task_id]
    return {"message": "Tarea eliminada"}

@app.get("/platforms")
async def get_platforms():
    """Obtener plataformas disponibles"""
    return {
        "available_platforms": [
            {"name": "twitter", "display_name": "Twitter"},
            {"name": "tiktok", "display_name": "TikTok"},
            {"name": "facebook", "display_name": "Facebook"}
        ]
    }

@app.get("/health")
async def health_check():
    """Estado de la API"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0"
    }

@app.get("/")
async def root():
    """Información de la API"""
    return {
        "name": "Multi-Platform Social Media Search API",
        "version": "3.0.0",
        "supported_platforms": ["twitter", "tiktok", "facebook"],
        "endpoints": [
            "POST /search - Iniciar búsqueda",
            "GET /progress/{task_id} - Ver progreso",
            "GET /results/{task_id} - Obtener resultados",
            "POST /report - Generar reporte IA",
            "GET /tasks - Listar tareas",
            "GET /platforms - Ver plataformas",
            "WS /ws/{task_id} - WebSocket para progreso en tiempo real"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)