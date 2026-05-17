import logging
from typing import Optional

from app.models.insurance import ChatResponse
from app.services.InsuranceExtractionService import InsuranceExtractionService
from app.services.response_extractor import extract_response_structure
from app.strategies.Workflows.copay_agent.agent import run_copay_agent

logger = logging.getLogger(__name__)


class InsuranceManager:
    """
    Orchestrates two insurance use cases:
    1. Admin PDF upload → extraction → MongoDB knowledge base
    2. Patient chat → ReAct agent → structured copay response
    """

    def __init__(self):
        self._extraction_service: Optional[InsuranceExtractionService] = None

    def _get_extraction_service(self) -> InsuranceExtractionService:
        if self._extraction_service is None:
            self._extraction_service = InsuranceExtractionService()
        return self._extraction_service

    async def upload_insurance_pdf(self, pdf_content: bytes, filename: str, nombre_seguro: str) -> dict:
        """Process an insurance document and store it in MongoDB.

        Excel (.xlsx) files are treated as medical network directories;
        PDFs are treated as policy documents.
        """
        service = self._get_extraction_service()
        if filename.lower().endswith(".xlsx"):
            return await service.process_network_directory(pdf_content, filename, nombre_seguro)
        return await service.process_pdf(pdf_content, filename, nombre_seguro)

    def chat(self, message: str, session_id: str) -> ChatResponse:
        """Run the copay agent and return a structured response."""
        logger.info(f"Chat: session={session_id} message_len={len(message)}")
        reply = run_copay_agent(user_message=message, session_id=session_id)
        structured = extract_response_structure(reply)
        return ChatResponse(reply=reply, session_id=session_id, **structured)
