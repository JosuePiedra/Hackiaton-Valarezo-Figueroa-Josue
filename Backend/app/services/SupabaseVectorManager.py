import os
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from uuid import uuid4
import logging
from supabase.client import Client, create_client
from langchain_community.vectorstores import SupabaseVectorStore
logger = logging.getLogger(__name__)
load_dotenv()
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY')
supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
embeddings = GoogleGenerativeAIEmbeddings(model='models/text-embedding-004', google_api_key=os.getenv('GEMINI_API_KEY'))

class SupabaseVectorManager:

    def __init__(self, table_name: str=os.getenv('SUPABASE_TABLE_NAME')):
        self.table_name = table_name
        self.vector_store = SupabaseVectorStore(client=supabase_client, embedding=embeddings, table_name=self.table_name, query_name='hybrid_search')

    def create_table(self):
        """Crea la tabla en Supabase si no existe"""
        try:
            logger.info(f'Verificando si existe la tabla {self.table_name}')
            supabase_client.table(self.table_name).select('id').limit(1).execute()
            logger.info(f'La tabla {self.table_name} ya existe')
        except Exception as e:
            logger.info(f'Creando tabla {self.table_name}...')
            try:
                result = supabase_client.rpc('create_vector_table_platon_user', {'table_name': self.table_name}).execute()
                logger.info(f'Resultado de RPC: {result.data}')
                logger.info(f'Tabla {self.table_name} creada exitosamente')
                return True
            except Exception as create_error:
                logger.error(f'Error al crear tabla: {str(create_error)}')
                raise create_error

    def table_exists(self) -> bool:
        """
        Verifica si la tabla vectorial existe en Supabase.
        
        Returns:
            bool: True si la tabla existe, False en caso contrario
        """
        try:
            logger.info(f'Verificando si existe la tabla {self.table_name}')
            supabase_client.table(self.table_name).select('id').limit(1).execute()
            logger.info(f'La tabla {self.table_name} existe en Supabase')
            return True
        except Exception as e:
            if '404' in str(e) or 'not found' in str(e).lower():
                logger.info(f'La tabla {self.table_name} no existe en Supabase')
                return False
            else:
                logger.warning(f'Error al verificar la existencia de la tabla {self.table_name}: {str(e)}')
                return False

    def add_documents(self, documents: List[Document], table_name: str):
        """Agrega documentos a Supabase"""
        try:
            ids = [str(uuid4()) for _ in documents]
            results = self.vector_store.add_documents(documents, ids=ids)
            return {'status': 'success', 'inserted_ids': ids, 'count': len(documents), 'results': results}
        except Exception as e:
            logger.error(f'Error adding documents: {str(e)}')
            return {'status': 'error', 'message': str(e)}

    def similarity_search(self, query: str, k: int=3, filter: Optional[Dict]=None) -> Dict[str, Any]:
        """Búsqueda semántica con filtros"""
        try:
            if filter:
                result = self.vector_store.similarity_search(query, k=k, filter=filter)
            else:
                result = self.vector_store.similarity_search(query, k=k)
            return self._format_results(result)
        except Exception as e:
            logger.error(f'Search error: {str(e)}')
            return {'error': str(e)}

    def hybrid_search(self, collection_name: str, query_data: dict) -> Dict[str, Any]:
        """
        Realiza una búsqueda híbrida (semántica + full-text) usando PostgreSQL.

        Args:
            query_data (dict): Datos para la búsqueda con las siguientes claves:
                - query: Texto de la consulta
                - match_count: Número máximo de resultados (default: 10)
                - full_text_weight: Peso para búsqueda full-text (default: 1.0)
                - semantic_weight: Peso para búsqueda semántica (default: 1.0)

        Returns:
            Dict[str, Any]: Resultados de la búsqueda
        """
        logger = logging.getLogger(__name__)
        logger.debug(f'Iniciando búsqueda híbrida en colección: {self.table_name}')
        supabase = self.supabase
        try:
            query_text = query_data.get('query')
            if not query_text:
                raise ValueError("Se requiere el parámetro 'query'")
            match_count = query_data.get('match_count', 10)
            full_text_weight = query_data.get('full_text_weight', 1.0)
            semantic_weight = query_data.get('semantic_weight', 1.0)
            embeddings = GoogleGenerativeAIEmbeddings(model='models/text-embedding-004', google_api_key=os.getenv('GEMINI_API_KEY'))
            query_embedding = embeddings.embed_query(query_text)
            response = supabase.rpc('hybrid_search', {'query_text': query_text, 'query_embedding': query_embedding, 'match_count': match_count, 'full_text_weight': full_text_weight, 'semantic_weight': semantic_weight, 'table_name': collection_name}).execute()
            results = []
            for item in response.data:
                result = {'id': item.get('id'), 'content': item.get('content'), 'metadata': item.get('metadata'), 'score': 1.0 / (50 + item.get('full_text_rank', 0)) * full_text_weight + 1.0 / (50 + item.get('semantic_rank', 0)) * semantic_weight, 'source': item.get('metadata', {}).get('source')}
                results.append(result)
            sorted_results = sorted(results, key=lambda x: x['score'], reverse=True)[:match_count]
            return {'status': 200, 'query': query_text, 'collection': collection_name, 'results_count': len(sorted_results), 'results': sorted_results}
        except ValueError as e:
            raise e
        except Exception as e:
            logger.error(f'Error en búsqueda híbrida: {str(e)}')
            raise Exception(f'Error en búsqueda híbrida: {str(e)}')

    @staticmethod
    def _format_results(results):
        """Formatea resultados de LangChain"""
        return {'results': [{'content': doc.page_content, 'metadata': doc.metadata, 'score': doc.metadata.get('similarity', 0)} for doc in results]}

    def _format_rpc_results(self, results):
        """Formatea resultados de RPC"""
        return {'results': [{'id': item['id'], 'content': item['content'], 'metadata': item['metadata'], 'score': self._calculate_combined_score(item)} for item in results]}

    @staticmethod
    def _calculate_combined_score(item):
        """Calcula score combinado según tu lógica de negocio"""
        semantic_score = 1 - item.get('semantic_rank', 0)
        fulltext_score = item.get('fulltext_rank', 0)
        return semantic_score * 0.6 + fulltext_score * 0.4

    @staticmethod
    def generate_document_description(text: str) -> str:
        llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash-lite', temperature=0, api_key=os.getenv('GEMINI_API_KEY'), max_tokens=None, timeout=None, max_retries=2)
        messages = [('system', 'Dado el siguiente contenido extraído de un documento, proporciona una descripción concisa que resuma los puntos clave que puedan ser utilizadas para identificar a este documento.'), ('human', f'{text}')]
        ai_msg = llm.invoke(messages)
        return ai_msg.content
    async def process_files(self, file_contents: List[tuple[str, bytes]], user_id: str):
        """Procesa PDFs con OCR, los divide en chunks y los guarda en Supabase."""
        from app.services.mistral_ocr import MistralOcrService
        from app.utils.text_splitter import split_text
        from langchain_core.documents import Document
        
        logger.info(f"Procesando {len(file_contents)} archivos para el usuario {user_id}...")
        
        try:
            ocr = MistralOcrService()
            docs = []
            
            for filename, content in file_contents:
                logger.info(f"Extrayendo texto de {filename}...")
                markdown_text = ocr.process_pdf(content)
                if not markdown_text:
                    logger.warning(f"No se pudo extraer texto de {filename}")
                    continue
                    
                logger.info(f"Dividiendo texto de {filename} en chunks...")
                chunks = split_text(markdown_text, size=1000, overlap=200)
                
                for i, chunk in enumerate(chunks):
                    docs.append(Document(
                        page_content=chunk,
                        metadata={"source": filename, "chunk": i, "user_id": user_id}
                    ))
                    
            if docs:
                logger.info(f"Guardando {len(docs)} chunks en Supabase tabla {self.table_name}...")
                self.add_documents(docs, table_name=self.table_name)
                logger.info(f"Archivos procesados y guardados con éxito.")
            else:
                logger.warning("No se generaron documentos para guardar.")
                
        except Exception as e:
            logger.error(f"Error en process_files: {str(e)}")
