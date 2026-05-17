import logging
import asyncio
from typing import List, Optional, Any, Dict, Callable
from fastapi import APIRouter, HTTPException, Path, Query, UploadFile, File, Body, Request
from functools import wraps
from app.services.SupabaseVectorManager import SupabaseVectorManager
from app.models.supabase_vector_store import SimilaritySearchResponse, UploadResponse, HybridSearchRequest, HybridSearchResponse
logger = logging.getLogger(__name__)
router = APIRouter()

def handle_exceptions(func: Callable):
    """
    Decorator for standardized exception handling in API endpoints.
    Logs errors and returns appropriate HTTP exceptions.
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException as e:
            raise
        except Exception as e:
            error_message = str(e)
            logger.error(f'Error in {func.__name__}: {error_message}')
            raise HTTPException(status_code=500, detail=error_message)
    return wrapper

def get_vector_manager(collection_name: str=None) -> SupabaseVectorManager:
    """Gets a SupabaseVectorManager instance for the specified collection"""
    return SupabaseVectorManager(table_name=collection_name)

@router.post('/upload_user_documents', summary='Subir y procesar documentos del usuario (PDF/CSV)', description='\n    Sube y procesa múltiples archivos PDF o CSV, almacenándolos en una colección específica de Supabase para el usuario autenticado.\n    El nombre de la colección se generará usando el `collection_prefix` y el ID del usuario.\n\n    Parámetros de formulario:\n    - files (List[UploadFile]): Lista de archivos PDF o CSV a procesar.\n    - collection_prefix (str, opcional): Prefijo para el nombre de la colección (por defecto "user_docs").\n\n    Respuestas:\n    - 202: Documentos recibidos y en proceso de carga y vectorización.\n    - 400: Formato de archivo no soportado (solo PDF o CSV).\n    - 500: Error interno del servidor.\n    ', responses={202: {'description': 'Documentos en proceso de carga', 'content': {'application/json': {'example': {'status': 202, 'message': 'Documentos en proceso de carga', 'data': {'status': 'processing', 'files': [{'filename': 'documento1.pdf', 'status': 'pending'}]}}}}}, 400: {'description': 'Formato de archivo no soportado'}, 500: {'description': 'Error interno del servidor'}})
@handle_exceptions
async def upload_user_documents_endpoint(request: Request, files: List[UploadFile]=File(..., description='List of PDF files to process'), collection_prefix: str=Query('user_docs', description='Prefix for the user collection')):
    """Processes and stores multiple PDF documents in a user-specific Supabase collection."""
    user_id = request.state.user['id']
    collection_name = f'{collection_prefix}_{user_id}'
    file_contents = []
    for file in files:
        file_ext = file.filename.split('.')[-1].lower()
        if file_ext not in ['pdf', 'csv']:
            raise HTTPException(status_code=400, detail={'status': 400, 'message': f'Formato no soportado: {file.filename}', 'data': None})
        content = await file.read()
        file_contents.append((file.filename, content))
    supabase_manager = SupabaseVectorManager(table_name=collection_name)
    supabase_manager.create_table()
    asyncio.create_task(supabase_manager.process_files(file_contents, user_id))
    return {'status': 202, 'message': 'Documentos en proceso de carga', 'data': {'status': 'processing', 'files': [{'filename': f.filename, 'status': 'pending'} for f in files]}}

@router.get('/similarity_search', summary='Realizar búsqueda por similitud semántica en una colección', description='\n    Busca documentos en una colección de Supabase que sean semánticamente similares a un texto de consulta.\n    Permite filtrar por fuentes (archivos de origen) específicas.\n\n    Parámetros de consulta:\n    - collection_name (str): Nombre de la colección donde realizar la búsqueda.\n    - query (str): Texto de consulta para la búsqueda por similitud.\n    - k (int, opcional): Número de resultados más similares a retornar (por defecto 2).\n    - sources (List[str], opcional): Lista de nombres de archivo (fuentes) para filtrar los resultados.\n\n    Respuestas:\n    - 200: Búsqueda realizada exitosamente, devuelve los documentos encontrados.\n    - 500: Error interno del servidor durante la búsqueda.\n    ', responses={200: {'description': 'Búsqueda realizada exitosamente', 'content': {'application/json': {'example': {'status': 200, 'message': 'Búsqueda realizada exitosamente', 'data': {'results': [{'content': 'Texto del documento similar...', 'metadata': {'source': 'archivo1.pdf', 'page': 3}, 'score': 0.89}, {'content': 'Otro texto relevante...', 'metadata': {'source': 'archivo2.pdf', 'page': 1}, 'score': 0.85}]}}}}}, 500: {'description': 'Error en la búsqueda por similitud'}})
@handle_exceptions
async def similarity_search_endpoint(collection_name: str=Query(..., description='Nombre de la colección'), query: str=Query(..., description='Texto de búsqueda'), k: int=Query(2, description='Número de resultados a retornar'), sources: Optional[List[str]]=Query(None, description='Filtrar por fuentes específicas')):
    """Búsqueda semántica con filtros opcionales."""
    vector_manager = get_vector_manager(collection_name)
    filter_search = {'source': {'$in': sources}} if sources else None
    result = vector_manager.similarity_search(query, k=k, filter=filter_search)
    if 'error' in result:
        raise HTTPException(status_code=500, detail={'status': 500, 'message': result['error'], 'data': None})
    return {'status': 200, 'message': 'Búsqueda realizada exitosamente', 'data': {'results': [{'content': item['content'], 'metadata': item['metadata'], 'score': item['score']} for item in result['results']]}}

@router.post('/hybrid_search', summary='Realizar búsqueda híbrida (semántica y texto completo)', description='\n    Ejecuta una búsqueda híbrida en una colección de Supabase, combinando la relevancia de la búsqueda semántica (vectorial)\n    con la precisión de la búsqueda de texto completo (keywords).\n\n    Parámetros de consulta:\n    - collection_name (str): Nombre de la colección donde realizar la búsqueda.\n\n    Body (HybridSearchRequest):\n    - query (str): Texto de consulta.\n    - match_count (int, opcional): Número de resultados a retornar (por defecto 10).\n    - fulltext_weight (float, opcional): Peso asignado a los resultados de búsqueda de texto completo (0.0 a 1.0, por defecto 0.5).\n    - semantic_weight (float, opcional): Peso asignado a los resultados de búsqueda semántica (0.0 a 1.0, por defecto 0.5).\n\n    Respuestas:\n    - 200: Búsqueda híbrida realizada exitosamente.\n    - 4xx/5xx: Errores durante la búsqueda (ej. colección no encontrada, error interno).\n    ', responses={200: {'description': 'Búsqueda híbrida realizada exitosamente', 'content': {'application/json': {'example': {'status': 200, 'message': 'Búsqueda híbrida realizada exitosamente', 'data': {'results': [{'content': 'Contenido del documento relevante...', 'metadata': {'source': 'fuente.pdf'}, 'score': 0.92}]}}}}}, 500: {'description': 'Error en la búsqueda híbrida'}})
@handle_exceptions
async def hybrid_search_endpoint(collection_name: str=Query(..., description='Nombre de la colección'), query_data: HybridSearchRequest=Body(..., description='Parámetros de búsqueda')):
    """Búsqueda híbrida que combina búsqueda de texto completo y semántica."""
    search_params = {'query': query_data.query, 'match_count': query_data.match_count, 'full_text_weight': query_data.fulltext_weight, 'semantic_weight': query_data.semantic_weight}
    vector_manager = get_vector_manager(collection_name)
    result = vector_manager.hybrid_search(search_params)
    if result['status'] != 200:
        raise HTTPException(status_code=result['status'], detail={'status': result['status'], 'message': result.get('error', 'Error desconocido en la búsqueda híbrida'), 'data': None})
    return {'status': 200, 'message': 'Búsqueda híbrida realizada exitosamente', 'data': {'results': result['results']}}