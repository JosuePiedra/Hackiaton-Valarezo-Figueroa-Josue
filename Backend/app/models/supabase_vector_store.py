# app/models/vector_store.py
from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field


class CollectionResponse(BaseModel):
    """Respuesta para operaciones relacionadas con colecciones"""
    status: int = Field(200, description="Código de estado HTTP")
    message: str = Field(..., description="Mensaje informativo sobre la operación")


class DeleteDocumentsRequest(BaseModel):
    """Solicitud para eliminar documentos por ID"""
    ids: List[str] = Field(..., description="Lista de IDs de documentos a eliminar")


class DeleteDocumentsResponse(BaseModel):
    """Respuesta a la eliminación de documentos"""
    status: int = Field(200, description="Código de estado HTTP")
    message: str = Field(..., description="Mensaje informativo sobre la operación")
    deleted_ids: List[str] = Field(..., description="IDs de los documentos eliminados")


class DocumentResult(BaseModel):
    """Resultado individual de una búsqueda"""
    content: str = Field(..., description="Contenido del documento")
    metadata: Dict[str, Any] = Field(..., description="Metadatos del documento")
    score: float = Field(..., description="Puntuación de relevancia (0-1)")


class SimilaritySearchResponse(BaseModel):
    """Respuesta a una búsqueda de similitud"""
    status: int = Field(200, description="Código de estado HTTP")
    data: List[DocumentResult] = Field(..., description="Resultados de la búsqueda")


class UploadResponse(BaseModel):
    """
    Respuesta del endpoint de carga de documentos
    """
    status: int
    message: str
    data: Dict[str, Union[List[Dict[str, str] | str], str]] = Field(..., description="Datos de respuesta")


class CollectionInfoResponse(BaseModel):
    """Respuesta con información de una colección"""
    status: int = Field(200, description="Código de estado HTTP")
    collection: Optional[str] = Field(None, description="Nombre de la colección")
    document_count: int = Field(..., description="Número de documentos en la colección")
    documents: Optional[List[Dict[str, Any]]] = Field(None, description="Muestra de documentos")


class HybridSearchRequest(BaseModel):
    """Solicitud para búsqueda híbrida"""
    query: str = Field(..., description="Texto de búsqueda")
    match_count: int = Field(10, description="Número máximo de resultados")
    fulltext_weight: float = Field(0.4, description="Peso para búsqueda de texto completo (0-1)")
    semantic_weight: float = Field(0.6, description="Peso para búsqueda semántica (0-1)")


class HybridSearchResponse(BaseModel):
    """Respuesta a una búsqueda híbrida"""
    status: int = Field(200, description="Código de estado HTTP")
    results: List[Dict[str, Any]] = Field(..., description="Resultados de la búsqueda")


class GetEntireCollectionRequest(BaseModel):
    """Solicitud para obtener toda la colección"""
    page_size: int = Field(100, description="Número máximo de documentos por página")
    page: int = Field(1, description="Número de página a obtener")
    filters: Optional[Dict[str, Any]] = Field(None, description="Filtros opcionales para aplicar a la consulta")
    collection_name: Optional[str] = Field(None, description="Nombre de la colección (opcional)")


class GetEntireCollectionResponse(BaseModel):
    """Respuesta con toda la colección"""
    status: int = Field(200, description="Código de estado HTTP")
    collection: str = Field(..., description="Nombre de la colección")
    document_count: int = Field(..., description="Número total de documentos")
    total_pages: int = Field(..., description="Número total de páginas")
    current_page: int = Field(..., description="Página actual")
    documents: List[Dict[str, Any]] = Field(..., description="Documentos de la colección")


class GetDocumentsInChunksRequest(BaseModel):
    """Solicitud para obtener documentos en chunks"""
    chunk_size: int = Field(5, description="Tamaño de cada chunk")
    collection_name: Optional[str] = Field(None, description="Nombre de la colección (opcional)")


class GetDocumentsInChunksResponse(BaseModel):
    """Respuesta con documentos divididos en chunks"""
    status: int = Field(200, description="Código de estado HTTP")
    collection: str = Field(..., description="Nombre de la colección")
    total_chunks: int = Field(..., description="Número total de chunks")
    total_documents: int = Field(..., description="Número total de documentos")
    chunks: List[List[Dict[str, Any]]] = Field(..., description="Documentos divididos en chunks")

class DeleteCollectionResponse(BaseModel):
    status: int
    message: str
    data: Dict[str, Any]
