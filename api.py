from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import asyncio
import uuid
from datetime import datetime
from enum import Enum
import threading
from concurrent.futures import ThreadPoolExecutor
import json
import re
from textblob import TextBlob
import openai
import os
from dotenv import load_dotenv

from x import scrape

load_dotenv()

app = FastAPI(title="Social Media Search API", description="API para búsquedas en redes sociales con análisis de sentimientos", version="2.0.0")

# Configurar OpenAI API key
openai.api_key = os.getenv("OPENAI_API_KEY")

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class SentimentLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"

class SearchRequest(BaseModel):
    query: str
    max_results: Optional[int] = 15
    platform: Optional[str] = "twitter"
    max_workers: Optional[int] = 5
    analyze_sentiment: Optional[bool] = True

class ReportRequest(BaseModel):
    task_id: str
    report_type: Optional[str] = "summary"  # summary, detailed, trends
    language: Optional[str] = "es"

class SentimentAnalysis(BaseModel):
    label: SentimentLabel
    score: float
    confidence: float

class PostData(BaseModel):
    url: str
    content: Optional[str] = None
    user: Optional[str] = None
    created_at: Optional[str] = None
    retweet_count: Optional[int] = 0
    favorite_count: Optional[int] = 0
    sentiment: Optional[SentimentAnalysis] = None
    keywords: Optional[List[str]] = None
    error: Optional[str] = None

class TaskInfo(BaseModel):
    task_id: str
    status: TaskStatus
    query: str
    platform: str
    progress: Dict[str, Any]
    results: Optional[List[PostData]] = None
    total: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    sentiment_summary: Optional[Dict[str, Any]] = None

class SearchResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str
    estimated_time: Optional[str] = None

class ProgressResponse(BaseModel):
    task_id: str
    status: TaskStatus
    query: str
    platform: str
    progress: Dict[str, Any]
    results: Optional[List[PostData]] = None
    total: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    sentiment_summary: Optional[Dict[str, Any]] = None

class AIReportResponse(BaseModel):
    task_id: str
    report_type: str
    generated_at: datetime
    report: str
    key_insights: List[str]
    sentiment_overview: Dict[str, Any]
    recommendations: List[str]

# Almacenamiento en memoria
tasks_storage: Dict[str, TaskInfo] = {}

class SentimentAnalyzer:
    """Clase para análisis de sentimientos"""
    
    @staticmethod
    def analyze_sentiment(text: str) -> SentimentAnalysis:
        """
        Analiza el sentimiento de un texto usando TextBlob
        """
        if not text or text.strip() == "":
            return SentimentAnalysis(
                label=SentimentLabel.NEUTRAL,
                score=0.0,
                confidence=0.0
            )
        
        try:
            # Limpiar texto
            cleaned_text = SentimentAnalyzer.clean_text(text)
            
            # Análisis con TextBlob
            blob = TextBlob(cleaned_text)
            polarity = blob.sentiment.polarity
            subjectivity = blob.sentiment.subjectivity
            
            # Determinar etiqueta
            if polarity > 0.1:
                label = SentimentLabel.POSITIVE
            elif polarity < -0.1:
                label = SentimentLabel.NEGATIVE
            else:
                label = SentimentLabel.NEUTRAL
            
            # Calcular confianza basada en la subjetividad
            confidence = min(abs(polarity) + subjectivity, 1.0)
            
            return SentimentAnalysis(
                label=label,
                score=polarity,
                confidence=confidence
            )
            
        except Exception as e:
            return SentimentAnalysis(
                label=SentimentLabel.NEUTRAL,
                score=0.0,
                confidence=0.0
            )
    
    @staticmethod
    def clean_text(text: str) -> str:
        """Limpia el texto para análisis"""
        # Remover URLs
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        # Remover menciones
        text = re.sub(r'@[A-Za-z0-9_]+', '', text)
        # Remover hashtags (mantener el texto)
        text = re.sub(r'#([A-Za-z0-9_]+)', r'\1', text)
        # Remover caracteres especiales excesivos
        text = re.sub(r'[^\w\s]', ' ', text)
        # Remover espacios múltiples
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    @staticmethod
    def extract_keywords(text: str, top_n: int = 5) -> List[str]:
        """Extrae palabras clave del texto"""
        if not text:
            return []
        
        try:
            cleaned_text = SentimentAnalyzer.clean_text(text)
            blob = TextBlob(cleaned_text)
            
            # Obtener palabras con filtrado
            words = [word.lower() for word in blob.words 
                    if len(word) > 3 and word.isalpha()]
            
            # Contar frecuencias
            word_freq = {}
            for word in words:
                word_freq[word] = word_freq.get(word, 0) + 1
            
            # Ordenar por frecuencia
            sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)
            
            return [word for word, _ in sorted_words[:top_n]]
            
        except Exception:
            return []

class ProgressTracker:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.current_step = ""
        self.total_steps = 0
        self.completed_steps = 0
        self.details = {}
    
    def update_progress(self, step: str, completed: int = None, total: int = None, details: Dict = None):
        self.current_step = step
        if completed is not None:
            self.completed_steps = completed
        if total is not None:
            self.total_steps = total
        if details:
            self.details.update(details)
        
        if self.task_id in tasks_storage:
            tasks_storage[self.task_id].progress = {
                "current_step": self.current_step,
                "completed_steps": self.completed_steps,
                "total_steps": self.total_steps,
                "percentage": (self.completed_steps / self.total_steps * 100) if self.total_steps > 0 else 0,
                "details": self.details
            }

def calculate_sentiment_summary(results: List[PostData]) -> Dict[str, Any]:
    """Calcula resumen de sentimientos"""
    if not results:
        return {}
    
    sentiment_counts = {"positive": 0, "negative": 0, "neutral": 0}
    total_score = 0
    valid_results = 0
    
    for result in results:
        if result.sentiment and result.content:
            sentiment_counts[result.sentiment.label] += 1
            total_score += result.sentiment.score
            valid_results += 1
    
    if valid_results == 0:
        return {}
    
    return {
        "total_analyzed": valid_results,
        "sentiment_distribution": {
            "positive": sentiment_counts["positive"],
            "negative": sentiment_counts["negative"],
            "neutral": sentiment_counts["neutral"]
        },
        "sentiment_percentages": {
            "positive": round((sentiment_counts["positive"] / valid_results) * 100, 2),
            "negative": round((sentiment_counts["negative"] / valid_results) * 100, 2),
            "neutral": round((sentiment_counts["neutral"] / valid_results) * 100, 2)
        },
        "average_sentiment_score": round(total_score / valid_results, 3),
        "dominant_sentiment": max(sentiment_counts, key=sentiment_counts.get)
    }

def run_scraping_task(task_id: str, query: str, max_results: int, platform: str, max_workers: int, analyze_sentiment: bool = True):
    """Ejecuta la tarea de scraping con análisis de sentimientos"""
    try:
        tasks_storage[task_id].status = TaskStatus.IN_PROGRESS
        tracker = ProgressTracker(task_id)
        
        tracker.update_progress("Iniciando scraping", 0, 100, {"substep": "Configurando driver"})
        
        def progress_callback(step: str, completed: int, total: int, details: Dict = None):
            tracker.update_progress(step, completed, total, details or {})
        
        if platform == "twitter":
            results = scrape_with_progress(query, max_results, max_workers, progress_callback)
        else:
            raise ValueError(f"Plataforma '{platform}' no soportada")
        
        # Procesar resultados y análisis de sentimientos
        tracker.update_progress("Analizando sentimientos", 85, 100)
        
        post_data = []
        for result in results:
            sentiment = None
            keywords = None
            
            if analyze_sentiment and result.get("text"):
                sentiment = SentimentAnalyzer.analyze_sentiment(result["text"])
                keywords = SentimentAnalyzer.extract_keywords(result["text"])
            
            post_data.append(PostData(
                url=result.get("url", ""),
                content=result.get("text"),
                user=result.get("user"),
                created_at=result.get("created_at"),
                retweet_count=result.get("retweet_count", 0),
                favorite_count=result.get("favorite_count", 0),
                sentiment=sentiment,
                keywords=keywords,
                error=result.get("error")
            ))
        
        # Calcular resumen de sentimientos
        sentiment_summary = calculate_sentiment_summary(post_data)
        
        tasks_storage[task_id].status = TaskStatus.COMPLETED
        tasks_storage[task_id].results = post_data
        tasks_storage[task_id].total = len(post_data)
        tasks_storage[task_id].sentiment_summary = sentiment_summary
        tasks_storage[task_id].completed_at = datetime.now()
        
        tracker.update_progress("Completado", 100, 100, {
            "message": f"Scraping completado con {len(post_data)} resultados",
            "sentiment_summary": sentiment_summary
        })
        
    except Exception as e:
        tasks_storage[task_id].status = TaskStatus.FAILED
        tasks_storage[task_id].error = str(e)
        tasks_storage[task_id].completed_at = datetime.now()
        tracker.update_progress("Error", 0, 100, {"error": str(e)})

def scrape_with_progress(query: str, max_results: int, max_workers: int, progress_callback):
    """Versión modificada de scrape que reporta progreso"""
    import time
    from x import get_headless_chrome_driver, open_twitter_login, go_to_explore, search_keyword, get_tweet_links, process_tweet_batch, save_to_csv, save_to_json
    
    driver = None
    
    try:
        progress_callback("Inicializando driver", 10, 100)
        driver = get_headless_chrome_driver()
        
        progress_callback("Realizando login", 20, 100)
        open_twitter_login(driver)
        
        progress_callback("Navegando a explorar", 30, 100)
        go_to_explore(driver)
        
        progress_callback("Buscando contenido", 40, 100)
        search_keyword(driver, query)
        
        progress_callback("Obteniendo enlaces", 50, 100)
        tweet_links = get_tweet_links(driver, max_results, extra_scrolls=20)
        
        if not tweet_links:
            progress_callback("Sin resultados", 100, 100)
            return []
        
        progress_callback("Procesando tweets", 60, 100, {"tweets_found": len(tweet_links)})
        
        def tweet_progress_callback(completed, total):
            percentage = 60 + (completed / total * 20)
            progress_callback("Procesando tweets", int(percentage), 100, {
                "tweets_processed": completed,
                "tweets_total": total
            })
        
        all_data = process_tweet_batch_with_progress(tweet_links, max_workers, tweet_progress_callback)
        
        progress_callback("Guardando datos", 80, 100)
        save_to_csv(all_data)
        save_to_json(all_data)
        
        return all_data
        
    except Exception as e:
        progress_callback("Error", 0, 100, {"error": str(e)})
        raise
    finally:
        if driver:
            driver.quit()

def process_tweet_batch_with_progress(tweet_links, max_workers, progress_callback):
    """Versión de process_tweet_batch que reporta progreso"""
    from x import scrape_tweet
    from concurrent.futures import ThreadPoolExecutor, as_completed
    
    all_data = []
    completed = 0
    total = len(tweet_links)
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(scrape_tweet, link): idx for idx, link in enumerate(tweet_links)}
        
        for future in as_completed(futures):
            result = future.result()
            all_data.append(result)
            completed += 1
            progress_callback(completed, total)
            
    return all_data

async def generate_ai_report(task_data: TaskInfo, report_type: str, language: str = "es") -> AIReportResponse:
    """Genera reporte usando OpenAI API"""
    
    if not task_data.results:
        raise HTTPException(status_code=400, detail="No hay datos para generar reporte")
    
    # Preparar datos para el prompt
    sentiment_summary = task_data.sentiment_summary or {}
    posts_sample = task_data.results[:10]  # Muestra de posts
    
    # Crear prompt según el tipo de reporte
    if report_type == "summary":
        prompt = f"""
        Analiza los siguientes datos de redes sociales sobre "{task_data.query}" y genera un resumen ejecutivo en {language}:

        Resumen de sentimientos:
        {json.dumps(sentiment_summary, indent=2)}

        Muestra de posts:
        {json.dumps([{"content": p.content, "sentiment": p.sentiment.label if p.sentiment else None, "keywords": p.keywords} for p in posts_sample], indent=2)}

        Genera un reporte ejecutivo que incluya:
        1. Resumen general de la situación
        2. Análisis de sentimientos predominantes
        3. Temas principales identificados
        4. Recomendaciones clave

        Responde en formato JSON con las siguientes claves:
        - "executive_summary": resumen ejecutivo
        - "key_insights": lista de insights principales
        - "recommendations": lista de recomendaciones
        """
    
    elif report_type == "detailed":
        prompt = f"""
        Genera un análisis detallado de los datos de redes sociales sobre "{task_data.query}" en {language}:

        Datos completos:
        - Total de posts analizados: {len(task_data.results)}
        - Distribución de sentimientos: {sentiment_summary.get('sentiment_percentages', {})}
        - Sentimiento promedio: {sentiment_summary.get('average_sentiment_score', 0)}

        Muestra de contenido:
        {json.dumps([{"content": p.content, "user": p.user, "sentiment": p.sentiment.label if p.sentiment else None, "retweet_count": p.retweet_count, "favorite_count": p.favorite_count} for p in posts_sample], indent=2)}

        Proporciona un análisis detallado en formato JSON con:
        - "detailed_analysis": análisis exhaustivo
        - "sentiment_insights": insights sobre sentimientos
        - "engagement_analysis": análisis de engagement
        - "key_insights": insights principales
        - "recommendations": recomendaciones detalladas
        """
    
    else:  # trends
        prompt = f"""
        Identifica tendencias y patrones en los datos sobre "{task_data.query}" en {language}:

        Análisis de tendencias basado en:
        - {len(task_data.results)} posts analizados
        - Sentimiento dominante: {sentiment_summary.get('dominant_sentiment', 'N/A')}
        - Distribución: {sentiment_summary.get('sentiment_distribution', {})}

        Datos de muestra:
        {json.dumps([{"content": p.content, "created_at": p.created_at, "sentiment": p.sentiment.label if p.sentiment else None, "keywords": p.keywords} for p in posts_sample], indent=2)}

        Genera análisis de tendencias en formato JSON con:
        - "trends_analysis": análisis de tendencias
        - "temporal_patterns": patrones temporales si aplica
        - "key_topics": temas principales
        - "key_insights": insights sobre tendencias
        - "recommendations": recomendaciones estratégicas
        """
    
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un experto analista de redes sociales y marketing digital. Proporciona análisis precisos y actionables."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        # Parsear respuesta JSON
        ai_response = response.choices[0].message.content
        
        try:
            parsed_response = json.loads(ai_response)
        except json.JSONDecodeError:
            # Si no es JSON válido, crear estructura básica
            parsed_response = {
                "executive_summary": ai_response,
                "key_insights": ["Análisis generado por IA"],
                "recommendations": ["Revisar datos manualmente"]
            }
        
        return AIReportResponse(
            task_id=task_data.task_id,
            report_type=report_type,
            generated_at=datetime.now(),
            report=parsed_response.get("executive_summary", parsed_response.get("detailed_analysis", parsed_response.get("trends_analysis", ai_response))),
            key_insights=parsed_response.get("key_insights", []),
            sentiment_overview=sentiment_summary,
            recommendations=parsed_response.get("recommendations", [])
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando reporte con IA: {str(e)}")

# ENDPOINTS

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, background_tasks: BackgroundTasks):
    """Endpoint para iniciar una búsqueda con análisis de sentimientos"""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="La búsqueda no puede estar vacía")
    
    task_id = str(uuid.uuid4())
    
    task_info = TaskInfo(
        task_id=task_id,
        status=TaskStatus.PENDING,
        query=query,
        platform=request.platform,
        progress={
            "current_step": "En cola",
            "completed_steps": 0,
            "total_steps": 100,
            "percentage": 0,
            "details": {}
        },
        created_at=datetime.now()
    )
    
    tasks_storage[task_id] = task_info
    
    background_tasks.add_task(
        run_scraping_task, 
        task_id, 
        query, 
        request.max_results, 
        request.platform,
        request.max_workers,
        request.analyze_sentiment
    )
    
    estimated_time = f"{request.max_results * 3} segundos aproximadamente"
    
    return SearchResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Búsqueda iniciada con análisis de sentimientos. Use /progress/{task_id} para consultar el estado.",
        estimated_time=estimated_time
    )

@app.get("/progress/{task_id}", response_model=ProgressResponse)
async def get_progress(task_id: str):
    """Endpoint para consultar el progreso de una tarea"""
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    task_info = tasks_storage[task_id]
    
    return ProgressResponse(
        task_id=task_info.task_id,
        status=task_info.status,
        query=task_info.query,
        platform=task_info.platform,
        progress=task_info.progress,
        results=task_info.results,
        total=task_info.total,
        created_at=task_info.created_at,
        completed_at=task_info.completed_at,
        error=task_info.error,
        sentiment_summary=task_info.sentiment_summary
    )

@app.post("/report", response_model=AIReportResponse)
async def generate_report(request: ReportRequest):
    """Endpoint para generar reporte con IA"""
    if request.task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    task_info = tasks_storage[request.task_id]
    
    if task_info.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="La tarea debe estar completada para generar reporte")
    
    return await generate_ai_report(task_info, request.report_type, request.language)

@app.get("/tasks", response_model=List[TaskInfo])
async def get_all_tasks():
    """Endpoint para obtener todas las tareas"""
    return list(tasks_storage.values())

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Endpoint para eliminar una tarea"""
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    del tasks_storage[task_id]
    return {"message": "Tarea eliminada exitosamente"}

@app.get("/")
async def root():
    """Endpoint raíz con información de la API"""
    return {
        "message": "Social Media Search API v2.0 - Con análisis de sentimientos y reportes IA",
        "platforms": ["twitter"],
        "features": [
            "Scraping de redes sociales",
            "Análisis de sentimientos",
            "Extracción de palabras clave",
            "Reportes generados por IA",
            "Seguimiento de progreso en tiempo real"
        ],
        "endpoints": [
            "POST /search - Iniciar búsqueda con análisis",
            "GET /progress/{task_id} - Consultar progreso",
            "POST /report - Generar reporte con IA",
            "GET /tasks - Listar todas las tareas",
            "DELETE /tasks/{task_id} - Eliminar tarea"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)