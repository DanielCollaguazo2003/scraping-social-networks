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

# Importar módulos de scraping
from x import scrape
from tiktok_scraping import TikTokScraper  # Importar la clase TikTokScraper

load_dotenv()

app = FastAPI(title="Multi-Platform Social Media Search API", description="API para búsquedas en múltiples redes sociales con análisis de sentimientos", version="3.0.0")

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
    platforms: Optional[List[str]] = ["twitter", "tiktok"]  # Múltiples plataformas
    max_workers: Optional[int] = 5
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
    platform: str  # Nueva field para identificar la plataforma
    url: str
    content: Optional[str] = None
    user: Optional[str] = None
    created_at: Optional[str] = None
    retweet_count: Optional[int] = 0
    favorite_count: Optional[int] = 0
    sentiment: Optional[SentimentAnalysis] = None
    keywords: Optional[List[str]] = None
    error: Optional[str] = None
    # Campos específicos para TikTok
    likes: Optional[int] = 0
    comments_count: Optional[int] = 0

class TaskInfo(BaseModel):
    task_id: str
    status: TaskStatus
    query: str
    platforms: List[str]  # Múltiples plataformas
    progress: Dict[str, Any]
    results: Optional[List[PostData]] = None
    platform_results: Optional[Dict[str, List[PostData]]] = None  # Resultados por plataforma
    total: int = 0
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    sentiment_summary: Optional[Dict[str, Any]] = None
    platform_summary: Optional[Dict[str, Dict[str, Any]]] = None  # Resumen por plataforma

class SearchResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: str
    platforms: List[str]
    estimated_time: Optional[str] = None

class ProgressResponse(BaseModel):
    task_id: str
    status: TaskStatus
    query: str
    platforms: List[str]
    progress: Dict[str, Any]
    results: Optional[List[PostData]] = None
    platform_results: Optional[Dict[str, List[PostData]]] = None
    total: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    sentiment_summary: Optional[Dict[str, Any]] = None
    platform_summary: Optional[Dict[str, Dict[str, Any]]] = None

class AIReportResponse(BaseModel):
    task_id: str
    report_type: str
    generated_at: datetime
    report: str
    key_insights: List[str]
    sentiment_overview: Dict[str, Any]
    platform_insights: Dict[str, Any]  # Insights por plataforma
    recommendations: List[str]

# Almacenamiento en memoria
tasks_storage: Dict[str, TaskInfo] = {}

class SentimentAnalyzer:
    """Clase para análisis de sentimientos"""
    
    @staticmethod
    def analyze_sentiment(text: str) -> SentimentAnalysis:
        """Analiza el sentimiento de un texto usando TextBlob"""
        if not text or text.strip() == "":
            return SentimentAnalysis(
                label=SentimentLabel.NEUTRAL,
                score=0.0,
                confidence=0.0
            )
        
        try:
            cleaned_text = SentimentAnalyzer.clean_text(text)
            blob = TextBlob(cleaned_text)
            polarity = blob.sentiment.polarity
            subjectivity = blob.sentiment.subjectivity
            
            if polarity > 0.1:
                label = SentimentLabel.POSITIVE
            elif polarity < -0.1:
                label = SentimentLabel.NEGATIVE
            else:
                label = SentimentLabel.NEUTRAL
            
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
        text = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', text)
        text = re.sub(r'@[A-Za-z0-9_]+', '', text)
        text = re.sub(r'#([A-Za-z0-9_]+)', r'\1', text)
        text = re.sub(r'[^\w\s]', ' ', text)
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
            
            words = [word.lower() for word in blob.words 
                    if len(word) > 3 and word.isalpha()]
            
            word_freq = {}
            for word in words:
                word_freq[word] = word_freq.get(word, 0) + 1
            
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
        self.platform_progress = {}
    
    def update_progress(self, step: str, completed: int = None, total: int = None, details: Dict = None, platform: str = None):
        self.current_step = step
        if completed is not None:
            self.completed_steps = completed
        if total is not None:
            self.total_steps = total
        if details:
            self.details.update(details)
        
        if platform:
            self.platform_progress[platform] = {
                "step": step,
                "completed": completed or 0,
                "total": total or 0,
                "details": details or {}
            }
        
        if self.task_id in tasks_storage:
            tasks_storage[self.task_id].progress = {
                "current_step": self.current_step,
                "completed_steps": self.completed_steps,
                "total_steps": self.total_steps,
                "percentage": (self.completed_steps / self.total_steps * 100) if self.total_steps > 0 else 0,
                "details": self.details,
                "platform_progress": self.platform_progress
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

def calculate_platform_summary(platform_results: Dict[str, List[PostData]]) -> Dict[str, Dict[str, Any]]:
    """Calcula resumen por plataforma"""
    platform_summary = {}
    
    for platform, results in platform_results.items():
        platform_summary[platform] = {
            "total_posts": len(results),
            "sentiment_summary": calculate_sentiment_summary(results),
            "engagement_metrics": calculate_engagement_metrics(results, platform)
        }
    
    return platform_summary

def calculate_engagement_metrics(results: List[PostData], platform: str) -> Dict[str, Any]:
    """Calcula métricas de engagement por plataforma"""
    if not results:
        return {}
    
    metrics = {}
    
    if platform == "twitter":
        total_retweets = sum(r.retweet_count or 0 for r in results)
        total_favorites = sum(r.favorite_count or 0 for r in results)
        metrics = {
            "total_retweets": total_retweets,
            "total_favorites": total_favorites,
            "avg_retweets": round(total_retweets / len(results), 2),
            "avg_favorites": round(total_favorites / len(results), 2)
        }
    
    elif platform == "tiktok":
        total_likes = sum(r.likes or 0 for r in results)
        total_comments = sum(r.comments_count or 0 for r in results)
        metrics = {
            "total_likes": total_likes,
            "total_comments": total_comments,
            "avg_likes": round(total_likes / len(results), 2),
            "avg_comments": round(total_comments / len(results), 2)
        }
    
    return metrics

async def scrape_twitter_data(query: str, max_results: int, max_workers: int, progress_callback, analyze_sentiment: bool = True):
    """Scraping de Twitter usando el módulo x.py existente"""
    try:
        progress_callback("Iniciando scraping de Twitter", 0, 100, {"substep": "Configurando driver"}, "twitter")
        
        def twitter_progress_callback(step: str, completed: int, total: int, details: Dict = None):
            progress_callback(step, completed, total, details or {}, "twitter")
        
        results = scrape_with_progress(query, max_results, max_workers, twitter_progress_callback)
        
        post_data = []
        for result in results:
            sentiment = None
            keywords = None
            
            if analyze_sentiment and result.get("text"):
                sentiment = SentimentAnalyzer.analyze_sentiment(result["text"])
                keywords = SentimentAnalyzer.extract_keywords(result["text"])
            
            post_data.append(PostData(
                platform="twitter",
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
        
        progress_callback("Twitter scraping completado", 100, 100, {"total_posts": len(post_data)}, "twitter")
        return post_data
        
    except Exception as e:
        progress_callback("Error en Twitter", 0, 100, {"error": str(e)}, "twitter")
        raise

async def scrape_tiktok_data(query: str, max_results: int, progress_callback, analyze_sentiment: bool = True):
    """Scraping de TikTok usando el TikTokScraper existente"""
    try:
        progress_callback("Iniciando scraping de TikTok", 0, 100, {"substep": "Configurando scraper"}, "tiktok")
        
        tiktok_scraper = TikTokScraper()
        
        # Configurar el scraper
        tiktok_scraper.setup_driver()
        await tiktok_scraper.setup_tiktok_api()
        
        progress_callback("Buscando videos en TikTok", 20, 100, {}, "tiktok")
        
        # Buscar videos
        videos_data = tiktok_scraper.search_videos(query, max_results)
        
        if not videos_data:
            progress_callback("No se encontraron videos en TikTok", 100, 100, {}, "tiktok")
            return []
        
        progress_callback("Extrayendo comentarios", 50, 100, {"videos_found": len(videos_data)}, "tiktok")
        
        # Extraer comentarios de los videos
        all_post_data = []
        
        for i, video_data in enumerate(videos_data):
            try:
                # Extraer comentarios usando la API
                comments = await tiktok_scraper.extract_comments_with_api(video_data['url'], video_data['numero'])
                
                # Crear post principal del video
                video_sentiment = None
                video_keywords = None
                
                if analyze_sentiment and video_data.get('descripcion'):
                    video_sentiment = SentimentAnalyzer.analyze_sentiment(video_data['descripcion'])
                    video_keywords = SentimentAnalyzer.extract_keywords(video_data['descripcion'])
                
                video_post = PostData(
                    platform="tiktok",
                    url=video_data['url'],
                    content=video_data['descripcion'],
                    user=video_data['usuario'],
                    created_at=datetime.now().isoformat(),
                    sentiment=video_sentiment,
                    keywords=video_keywords,
                    comments_count=len(comments)
                )
                
                all_post_data.append(video_post)
                
                # Crear posts para cada comentario
                for comment in comments:
                    comment_sentiment = None
                    comment_keywords = None
                    
                    if analyze_sentiment and comment.get('texto'):
                        comment_sentiment = SentimentAnalyzer.analyze_sentiment(comment['texto'])
                        comment_keywords = SentimentAnalyzer.extract_keywords(comment['texto'])
                    
                    comment_post = PostData(
                        platform="tiktok",
                        url=video_data['url'] + f"#comment_{comment['numero']}",
                        content=comment['texto'],
                        user=comment['autor'],
                        created_at=comment['timestamp'],
                        sentiment=comment_sentiment,
                        keywords=comment_keywords,
                        likes=comment.get('likes', 0)
                    )
                    
                    all_post_data.append(comment_post)
                
                # Actualizar progreso
                progress_percentage = 50 + ((i + 1) / len(videos_data)) * 40
                progress_callback(f"Procesando video {i+1}/{len(videos_data)}", 
                               int(progress_percentage), 100, 
                               {"video_processed": i+1, "total_videos": len(videos_data)}, 
                               "tiktok")
                
            except Exception as e:
                print(f"Error procesando video {i+1}: {e}")
                continue
        
        # Cerrar el scraper
        tiktok_scraper.close_driver()
        
        progress_callback("TikTok scraping completado", 100, 100, {"total_posts": len(all_post_data)}, "tiktok")
        return all_post_data
        
    except Exception as e:
        progress_callback("Error en TikTok", 0, 100, {"error": str(e)}, "tiktok")
        raise

async def run_multi_platform_scraping(task_id: str, query: str, max_results: int, platforms: List[str], max_workers: int, analyze_sentiment: bool = True):
    """Ejecuta scraping en múltiples plataformas simultáneamente"""
    try:
        tasks_storage[task_id].status = TaskStatus.IN_PROGRESS
        tracker = ProgressTracker(task_id)
        
        tracker.update_progress("Iniciando scraping multi-plataforma", 0, 100, {"platforms": platforms})
        
        def progress_callback(step: str, completed: int, total: int, details: Dict = None, platform: str = None):
            tracker.update_progress(step, completed, total, details or {}, platform)
        
        # Ejecutar scraping en paralelo para todas las plataformas
        scraping_tasks = []
        
        if "twitter" in platforms:
            scraping_tasks.append(scrape_twitter_data(query, max_results, max_workers, progress_callback, analyze_sentiment))
        
        if "tiktok" in platforms:
            scraping_tasks.append(scrape_tiktok_data(query, max_results, progress_callback, analyze_sentiment))
        
        # Ejecutar todas las tareas en paralelo
        results = await asyncio.gather(*scraping_tasks, return_exceptions=True)
        
        # Procesar resultados
        all_results = []
        platform_results = {}
        
        for i, result in enumerate(results):
            platform = platforms[i]
            
            if isinstance(result, Exception):
                print(f"Error en {platform}: {result}")
                platform_results[platform] = []
            else:
                platform_results[platform] = result
                all_results.extend(result)
        
        # Calcular resúmenes
        sentiment_summary = calculate_sentiment_summary(all_results)
        platform_summary = calculate_platform_summary(platform_results)
        
        # Actualizar estado de la tarea
        tasks_storage[task_id].status = TaskStatus.COMPLETED
        tasks_storage[task_id].results = all_results
        tasks_storage[task_id].platform_results = platform_results
        tasks_storage[task_id].total = len(all_results)
        tasks_storage[task_id].sentiment_summary = sentiment_summary
        tasks_storage[task_id].platform_summary = platform_summary
        tasks_storage[task_id].completed_at = datetime.now()
        
        tracker.update_progress("Completado", 100, 100, {
            "message": f"Scraping completado con {len(all_results)} resultados de {len(platforms)} plataformas",
            "sentiment_summary": sentiment_summary,
            "platform_summary": platform_summary
        })
        
    except Exception as e:
        tasks_storage[task_id].status = TaskStatus.FAILED
        tasks_storage[task_id].error = str(e)
        tasks_storage[task_id].completed_at = datetime.now()
        tracker.update_progress("Error", 0, 100, {"error": str(e)})

# Funciones auxiliares para Twitter (reutilizando código existente)
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
    """Genera reporte usando OpenAI API incluyendo análisis multi-plataforma"""
    
    if not task_data.results:
        raise HTTPException(status_code=400, detail="No hay datos para generar reporte")
    
    # Preparar datos para el prompt
    sentiment_summary = task_data.sentiment_summary or {}
    platform_summary = task_data.platform_summary or {}
    posts_sample = task_data.results[:15]  # Muestra de posts
    
    # Crear prompt específico para multi-plataforma
    if report_type == "summary":
        prompt = f"""
        Analiza los siguientes datos de múltiples redes sociales sobre "{task_data.query}" y genera un resumen ejecutivo en {language}:

        Plataformas analizadas: {', '.join(task_data.platforms)}

        Resumen general de sentimientos:
        {json.dumps(sentiment_summary, indent=2)}

        Resumen por plataforma:
        {json.dumps(platform_summary, indent=2)}

        Muestra de posts multi-plataforma:
        {json.dumps([{"platform": p.platform, "content": p.content, "user": p.user, "sentiment": p.sentiment.label if p.sentiment else None, "keywords": p.keywords} for p in posts_sample], indent=2)}

        Genera un reporte ejecutivo que incluya:
        1. Resumen general de la situación
        2. Comparación entre plataformas
        3. Análisis de sentimientos por plataforma
        4. Temas principales identificados
        5. Recomendaciones específicas por plataforma

        Responde en formato JSON con las siguientes claves:
        - "executive_summary": resumen ejecutivo
        - "platform_comparison": comparación entre plataformas
        - "key_insights": lista de insights principales
        - "recommendations": lista de recomendaciones
        """
    
    elif report_type == "detailed":
        prompt = f"""
        Genera un análisis detallado de los datos multi-plataforma sobre "{task_data.query}" en {language}:

        Plataformas: {', '.join(task_data.platforms)}
        Total de posts: {len(task_data.results)}

        Análisis por plataforma:
        {json.dumps(platform_summary, indent=2)}

        Muestra de contenido:
        {json.dumps([{"platform": p.platform, "content": p.content, "user": p.user, "sentiment": p.sentiment.label if p.sentiment else None, "engagement": {"retweets": p.retweet_count, "likes": p.likes}} for p in posts_sample], indent=2)}

        Proporciona un análisis detallado en formato JSON con:
        - "detailed_analysis": análisis exhaustivo
        - "platform_insights": insights específicos por plataforma
        - "cross_platform_patterns": patrones entre plataformas
        - "engagement_analysis": análisis de engagement por plataforma
        - "key_insights": insights principales
        - "recommendations": recomendaciones detalladas
        """
    
    else:  # trends
        prompt = f"""
        Identifica tendencias y patrones multi-plataforma para "{task_data.query}" en {language}:

        Datos analizados:
        - Plataformas: {', '.join(task_data.platforms)}
        - Total posts: {len(task_data.results)}
        - Resumen por plataforma: {json.dumps(platform_summary, indent=2)}

        Genera análisis de tendencias en formato JSON con:
        - "trends_analysis": análisis de tendencias generales
        - "platform_trends": tendencias específicas por plataforma
        - "cross_platform_insights": insights entre plataformas
        - "temporal_patterns": patrones temporales
        - "key_insights": insights sobre tendencias
        - "recommendations": recomendaciones estratégicas
        """
    
    try:
        response = await openai.ChatCompletion.acreate(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Eres un experto analista de redes sociales con experiencia en análisis multi-plataforma. Proporciona análisis precisos y actionables."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=2000,
            temperature=0.7
        )
        
        ai_response = response.choices[0].message.content
        
        try:
            parsed_response = json.loads(ai_response)
        except json.JSONDecodeError:
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
            platform_insights=parsed_response.get("platform_insights", {}),
            recommendations=parsed_response.get("recommendations", [])
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando reporte con IA: {str(e)}")

# ENDPOINTS

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, background_tasks: BackgroundTasks):
    """Endpoint para iniciar búsqueda multi-plataforma con análisis de sentimientos"""
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="La búsqueda no puede estar vacía")
    
    # Validar plataformas
    valid_platforms = ["twitter", "tiktok"]
    platforms = [p for p in request.platforms if p in valid_platforms]
    
    if not platforms:
        raise HTTPException(status_code=400, detail=f"Plataformas válidas: {valid_platforms}")
    
    task_id = str(uuid.uuid4())
    
    task_info = TaskInfo(
        task_id=task_id,
        status=TaskStatus.PENDING,
        query=query,
        platforms=platforms,
        progress={
            "current_step": "En cola",
            "completed_steps": 0,
            "total_steps": 100,
            "percentage": 0,
            "details": {},
            "platform_progress": {}
        },
        created_at=datetime.now()
    )
    
    tasks_storage[task_id] = task_info
    
    background_tasks.add_task(
        run_multi_platform_scraping, 
        task_id, 
        query, 
        request.max_results, 
        platforms,
        request.max_workers,
        request.analyze_sentiment
    )
    
    estimated_time = f"{request.max_results * len(platforms) * 2} segundos aproximadamente"
    
    return SearchResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message=f"Búsqueda iniciada en {len(platforms)} plataformas: {', '.join(platforms)}",
        platforms=platforms,
        estimated_time=estimated_time
    )

@app.get("/progress/{task_id}", response_model=ProgressResponse)
async def get_progress(task_id: str):
    """Endpoint para obtener el progreso de una tarea"""
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    task_info = tasks_storage[task_id]
    
    return ProgressResponse(
        task_id=task_info.task_id,
        status=task_info.status,
        query=task_info.query,
        platforms=task_info.platforms,
        progress=task_info.progress,
        results=task_info.results,
        platform_results=task_info.platform_results,
        total=task_info.total,
        created_at=task_info.created_at,
        completed_at=task_info.completed_at,
        error=task_info.error,
        sentiment_summary=task_info.sentiment_summary,
        platform_summary=task_info.platform_summary
    )

@app.get("/results/{task_id}")
async def get_results(task_id: str):
    """Endpoint para obtener resultados de una tarea completada"""
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    task_info = tasks_storage[task_id]
    
    if task_info.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="La tarea no está completada")
    
    return {
        "task_id": task_info.task_id,
        "query": task_info.query,
        "platforms": task_info.platforms,
        "total_results": task_info.total,
        "results": task_info.results,
        "platform_results": task_info.platform_results,
        "sentiment_summary": task_info.sentiment_summary,
        "platform_summary": task_info.platform_summary,
        "created_at": task_info.created_at,
        "completed_at": task_info.completed_at
    }

@app.post("/report", response_model=AIReportResponse)
async def generate_report(request: ReportRequest):
    """Endpoint para generar reportes con IA"""
    if request.task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    task_info = tasks_storage[request.task_id]
    
    if task_info.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="La tarea debe estar completada para generar reporte")
    
    report = await generate_ai_report(task_info, request.report_type, request.language)
    return report

@app.get("/tasks")
async def get_tasks():
    """Endpoint para obtener todas las tareas"""
    return {
        "tasks": [
            {
                "task_id": task.task_id,
                "status": task.status,
                "query": task.query,
                "platforms": task.platforms,
                "total_results": task.total,
                "created_at": task.created_at,
                "completed_at": task.completed_at,
                "error": task.error
            }
            for task in tasks_storage.values()
        ],
        "total_tasks": len(tasks_storage)
    }

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Endpoint para eliminar una tarea"""
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    del tasks_storage[task_id]
    return {"message": "Tarea eliminada correctamente"}

@app.get("/platforms")
async def get_platforms():
    """Endpoint para obtener las plataformas disponibles"""
    return {
        "available_platforms": [
            {
                "name": "twitter",
                "display_name": "Twitter",
                "description": "Red social de microblogging",
                "features": ["tweets", "retweets", "likes", "sentiment_analysis"]
            },
            {
                "name": "tiktok",
                "display_name": "TikTok",
                "description": "Plataforma de videos cortos",
                "features": ["videos", "comments", "likes", "sentiment_analysis"]
            }
        ]
    }

@app.get("/health")
async def health_check():
    """Endpoint de salud"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "3.0.0",
        "active_tasks": len([t for t in tasks_storage.values() if t.status == TaskStatus.IN_PROGRESS])
    }

@app.get("/")
async def root():
    """Endpoint raíz con información de la API"""
    return {
        "name": "Multi-Platform Social Media Search API",
        "version": "3.0.0",
        "description": "API para búsquedas en múltiples redes sociales con análisis de sentimientos",
        "supported_platforms": ["twitter", "tiktok"],
        "endpoints": {
            "search": "POST /search - Iniciar búsqueda multi-plataforma",
            "progress": "GET /progress/{task_id} - Obtener progreso de tarea",
            "results": "GET /results/{task_id} - Obtener resultados",
            "report": "POST /report - Generar reporte con IA",
            "tasks": "GET /tasks - Listar todas las tareas",
            "platforms": "GET /platforms - Obtener plataformas disponibles",
            "health": "GET /health - Estado de la API"
        }
    }
    
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)