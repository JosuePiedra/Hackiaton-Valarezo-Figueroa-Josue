import base64
import os
import logging

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)

OCR_PROMPT = (
    "Extrae todo el texto de este documento PDF en formato Markdown. "
    "Preserva la estructura original: tablas, listas, encabezados y secciones. "
    "No omitas ningún dato numérico ni nombre. No agregues comentarios propios."
)


class GeminiOcrService:
    """OCR vía Gemini Vision — envía el PDF como inline data y extrae el texto en Markdown."""

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY no está configurada.")
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            max_output_tokens=32768,
            thinking_budget=0,
            api_key=api_key,
        )

    def process_pdf(self, pdf_content: bytes) -> str:
        logger.info("Iniciando procesamiento de PDF con Gemini Vision OCR...")
        try:
            base64_pdf = base64.b64encode(pdf_content).decode("utf-8")
            message = HumanMessage(content=[
                {
                    "type": "media",
                    "mime_type": "application/pdf",
                    "data": base64_pdf,
                },
                {
                    "type": "text",
                    "text": OCR_PROMPT,
                },
            ])
            response = self.llm.invoke([message])
            markdown = response.content.strip()
            logger.info(f"Gemini Vision OCR completado: {len(markdown)} chars extraídos.")
            return markdown
        except Exception as e:
            logger.error(f"Error en Gemini Vision OCR: {e}", exc_info=True)
            return ""
