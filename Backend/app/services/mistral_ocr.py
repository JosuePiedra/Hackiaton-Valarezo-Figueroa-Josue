import base64
import os
from mistralai.client import Mistral
import logging

logger = logging.getLogger(__name__) # Logger para este módulo


class MistralOcrService:
    """
    Servicio para interactuar con la API de OCR de Mistral.
    """
    def __init__(self):
        self.api_key = os.getenv("MISTRAL_API_KEY")
        if not self.api_key:
            raise ValueError("La variable de entorno MISTRAL_API_KEY no está configurada.")
        self.client = Mistral(api_key=self.api_key)

    def process_pdf(self, pdf_content: bytes) -> str:
        """
        Procesa el contenido de un PDF usando la API de OCR de Mistral.

        Args:
            pdf_content: El contenido del archivo PDF en bytes.

        Returns:
            El contenido extraído del PDF en formato Markdown, o una cadena vacía si falla.
        """
        logger.info("Iniciando procesamiento de PDF con Mistral OCR...")
        try:
            # Codificar el contenido del PDF a Base64
            base64_pdf = base64.b64encode(pdf_content).decode('utf-8')

            # Llamar a la API de OCR
            ocr_response = self.client.ocr.process(
                model="mistral-ocr-latest",
                document={
                    "type": "document_url",
                    "document_url": f"data:application/pdf;base64,{base64_pdf}"
                },
                include_image_base64=False  # Lo ponemos en False para no aumentar el tamaño de la respuesta
            )

            # Convertir la respuesta a un diccionario de Python para un acceso fiable.
            response_dict = ocr_response.model_dump()

            # Extraer el contenido de cada página basándose en la estructura de diccionario.
            pages = response_dict.get('pages', [])
            if not pages:
                logger.warning("Mistral OCR devolvió una respuesta sin páginas.")
                return ""

            full_markdown_content = "\n\n".join([page.get('markdown', '') for page in pages])

            logger.info("Procesamiento con Mistral OCR completado exitosamente.")
            return full_markdown_content

        except Exception as e:
            logger.error(f"Error durante el procesamiento con Mistral OCR: {e}", exc_info=True)
            return ""
