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

# Asumiendo que tienes el módulo x con la función scrape
from x import scrape

app = FastAPI(title="Social Media Search API", description="API para búsquedas en redes sociales", version="1.0.0")

class TaskStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class SearchRequest(BaseModel):
    query: str
    max_results: Optional[int] = 15
    platform: Optional[str] = "twitter"
    max_workers: Optional[int] = 5

class PostData(BaseModel):
    url: str
    content: Optional[str] = None
    user: Optional[str] = None
    created_at: Optional[str] = None
    retweet_count: Optional[int] = 0
    favorite_count: Optional[int] = 0
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

# Almacenamiento en memoria para las tareas (en producción usar Redis o base de datos)
tasks_storage: Dict[str, TaskInfo] = {}

# Clase para manejar el progreso de las tareas
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
        
        # Actualizar en el almacenamiento
        if self.task_id in tasks_storage:
            tasks_storage[self.task_id].progress = {
                "current_step": self.current_step,
                "completed_steps": self.completed_steps,
                "total_steps": self.total_steps,
                "percentage": (self.completed_steps / self.total_steps * 100) if self.total_steps > 0 else 0,
                "details": self.details
            }

def run_scraping_task(task_id: str, query: str, max_results: int, platform: str, max_workers: int):
    """
    Ejecuta la tarea de scraping en segundo plano
    """
    try:
        # Actualizar estado a en progreso
        tasks_storage[task_id].status = TaskStatus.IN_PROGRESS
        
        # Crear tracker de progreso
        tracker = ProgressTracker(task_id)
        
        # Paso 1: Inicialización
        tracker.update_progress("Inicializando scraper", 0, 100, {"substep": "Configurando driver"})
        
        # Modificar la función scrape para aceptar un callback de progreso
        def progress_callback(step: str, completed: int, total: int, details: Dict = None):
            tracker.update_progress(step, completed, total, details or {})
        
        # Ejecutar scraping
        if platform == "twitter":
            results = scrape_with_progress(query, max_results, max_workers, progress_callback)
        else:
            raise ValueError(f"Plataforma '{platform}' no soportada")
        
        # Convertir resultados a PostData
        post_data = []
        for result in results:
            post_data.append(PostData(
                url=result.get("url", ""),
                content=result.get("text"),
                user=result.get("user"),
                created_at=result.get("created_at"),
                retweet_count=result.get("retweet_count", 0),
                favorite_count=result.get("favorite_count", 0),
                error=result.get("error")
            ))
        
        # Actualizar tarea como completada
        tasks_storage[task_id].status = TaskStatus.COMPLETED
        tasks_storage[task_id].results = post_data
        tasks_storage[task_id].total = len(post_data)
        tasks_storage[task_id].completed_at = datetime.now()
        
        tracker.update_progress("Completado", 100, 100, {"message": f"Scraping completado con {len(post_data)} resultados"})
        
    except Exception as e:
        # Actualizar tarea como fallida
        tasks_storage[task_id].status = TaskStatus.FAILED
        tasks_storage[task_id].error = str(e)
        tasks_storage[task_id].completed_at = datetime.now()
        
        tracker.update_progress("Error", 0, 100, {"error": str(e)})

def scrape_with_progress(query: str, max_results: int, max_workers: int, progress_callback):
    """
    Versión modificada de scrape que reporta progreso
    """
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
        
        # Función para reportar progreso durante el procesamiento
        def tweet_progress_callback(completed, total):
            percentage = 60 + (completed / total * 30)  # 60% a 90%
            progress_callback("Procesando tweets", int(percentage), 100, {
                "tweets_processed": completed,
                "tweets_total": total
            })
        
        all_data = process_tweet_batch_with_progress(tweet_links, max_workers, tweet_progress_callback)
        
        progress_callback("Guardando datos", 95, 100)
        save_to_csv(all_data)
        save_to_json(all_data)
        
        progress_callback("Completado", 100, 100)
        return all_data
        
    except Exception as e:
        progress_callback("Error", 0, 100, {"error": str(e)})
        raise
    finally:
        if driver:
            driver.quit()

def process_tweet_batch_with_progress(tweet_links, max_workers, progress_callback):
    """
    Versión de process_tweet_batch que reporta progreso
    """
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

@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest, background_tasks: BackgroundTasks):
    """
    Endpoint para iniciar una búsqueda en redes sociales
    """
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="La búsqueda no puede estar vacía")
    
    # Generar ID único para la tarea
    task_id = str(uuid.uuid4())
    
    # Crear entrada en el almacenamiento
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
    
    # Ejecutar tarea en segundo plano
    background_tasks.add_task(
        run_scraping_task, 
        task_id, 
        query, 
        request.max_results, 
        request.platform,
        request.max_workers
    )
    
    # Estimar tiempo
    estimated_time = f"{request.max_results * 2} segundos aproximadamente"
    
    return SearchResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="Búsqueda iniciada. Use el endpoint /progress/{task_id} para consultar el estado.",
        estimated_time=estimated_time
    )

@app.get("/progress/{task_id}", response_model=ProgressResponse)
async def get_progress(task_id: str):
    """
    Endpoint para consultar el progreso de una tarea
    """
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
        error=task_info.error
    )

@app.get("/tasks", response_model=List[TaskInfo])
async def get_all_tasks():
    """
    Endpoint para obtener todas las tareas
    """
    return list(tasks_storage.values())

@app.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """
    Endpoint para eliminar una tarea
    """
    if task_id not in tasks_storage:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    del tasks_storage[task_id]
    return {"message": "Tarea eliminada exitosamente"}

@app.get("/")
async def root():
    """
    Endpoint raíz
    """
    return {
        "message": "Social Media Search API",
        "platforms": ["twitter"],
        "endpoints": [
            "/search - Iniciar búsqueda",
            "/progress/{task_id} - Consultar progreso",
            "/tasks - Listar todas las tareas",
            "/tasks/{task_id} - Eliminar tarea"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)