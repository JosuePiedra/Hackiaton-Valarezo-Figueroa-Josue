import sys
from contextlib import asynccontextmanager

from app.adapters import (
    insurance
)
from app.services.Middleware.JWTMiddlewareProvider import JWTAuthMiddlewareProvider

# pyrefly: ignore [missing-import]
from fastapi import FastAPI
import logging
from fastapi.middleware.cors import CORSMiddleware

# ModelsPoolProvider needs to be adjusted or removed if not needed, assuming it's kept for now
# from app.services.ModelsPoolProvider import ModelPoolProvider

log_formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers.clear()
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(log_formatter)
root_logger.addHandler(console_handler)

logger = logging.getLogger(__name__)
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting app")
    # ModelPoolProvider.initialize_strategies()
    yield
    logger.info("Stopping app")


tags_metadata = [
    # {"name": "auth", "description": "Autenticación de usuarios y gestión de sesiones."},
    # {
    #     "name": "supabase_vector_store",
    #     "description": "Operaciones con Supabase como almacén vectorial.",
    # },
    {
        "name": "insurance",
        "description": "Agente estimador de copago — admin sube PDFs, paciente consulta cobertura.",
    },
]
app = FastAPI(
    lifespan=lifespan,
    title="RAG Core API",
    openapi_tags=tags_metadata,
    description="API minimalista para flujo RAG (Retrieval-Augmented Generation).",
)

# app.include_router(authUser.router, prefix="/api/v1/auth", tags=["auth"])
# app.include_router(
#     supabase_vector_store.router,
#     prefix="/api/v1/supabase",
#     tags=["supabase_vector_store"],
# )
app.include_router(insurance.router, prefix="/api/v1/insurance", tags=["insurance"])

app.add_middleware(JWTAuthMiddlewareProvider)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
