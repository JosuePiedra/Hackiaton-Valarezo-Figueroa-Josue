import logging
from functools import wraps
from typing import Callable

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status

from app.manager.InsuranceManager import InsuranceManager
from app.models.insurance import ChatRequest, ChatResponse

logger = logging.getLogger(__name__)
router = APIRouter()


def handle_exceptions(func: Callable):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))

    return wrapper


def _require_admin(request: Request) -> None:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required"
        )


@router.post(
    "/asdfhnjoasidjasidailosdiajsdqweqnwadsnjkdaushcasjkdaso/upload",
    summary="Admin: Upload insurance document (PDF or Excel)",
    description=(
        "Accepts PDF or .xlsx files. PDFs are processed via Mistral OCR; Excel files are "
        "parsed directly into markdown tables. In both cases Gemini extracts structured "
        "coverage rules which are stored in MongoDB scoped to the given nombre_seguro."
    ),
)
@handle_exceptions
async def upload_insurance_document(
    request: Request,
    file: UploadFile = File(..., description="Insurance policy PDF"),
    nombre_seguro: str = Form(
        ..., description="Identificador del plan (ej: CONFIPLUS-60K, SALUD-PLUS)"
    ),
):
    #  _require_admin(request)

    ALLOWED_EXTENSIONS = (".pdf", ".xlsx")
    if not any(file.filename.lower().endswith(ext) for ext in ALLOWED_EXTENSIONS):
        raise HTTPException(
            status_code=400, detail="Solo se aceptan archivos PDF o Excel (.xlsx)"
        )

    pdf_content = await file.read()
    if not pdf_content:
        raise HTTPException(status_code=400, detail="El archivo PDF está vacío")

    manager = InsuranceManager()
    result = await manager.upload_insurance_pdf(
        pdf_content, file.filename, nombre_seguro
    )
    return {
        "status": 200,
        "message": "Documento procesado exitosamente",
        "data": result,
    }


@router.post(
    "/dnjfasndashdqweojgkpsdjfmmknsabdkodfpoiucxzcasdqwm/chat",
    response_model=ChatResponse,
    summary="Patient: Chat with the copay estimation agent",
    description=(
        "Public endpoint — no authentication required. "
        "The patient describes their symptoms and the agent identifies the specialty, "
        "finds coverage rules via RAG, and calculates the estimated copay. "
        "Use a stable session_id to maintain conversation history."
    ),
)
@handle_exceptions
async def chat_with_agent(chat_request: ChatRequest):
    manager = InsuranceManager()
    return manager.chat(
        message=chat_request.message, session_id=chat_request.session_id
    )
