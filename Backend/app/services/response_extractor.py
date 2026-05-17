import json
import logging
import os

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
logger = logging.getLogger(__name__)

_PROMPT = """Analiza el siguiente mensaje de un asistente de seguros de salud ecuatoriano y extrae información estructurada.

Mensaje:
---
{reply}
---

Devuelve ÚNICAMENTE un objeto JSON válido (sin markdown, sin backticks) con esta estructura exacta:

{{
  "response_type": "plan_selection" | "coverage_info" | "general",
  "plans": null,
  "specialty": null,
  "estimated_copay": null,
  "requires_authorization": null,
  "waiting_period_days": null,
  "network_tier": null,
  "providers": null,
  "annual_deductible": null,
  "notes": null,
  "deductible_applies": null
}}

Reglas de clasificación:
- "plan_selection": el mensaje pregunta al paciente qué plan tiene Y lista opciones de planes → extrae los nombres de planes en el campo "plans" como array de strings
- "coverage_info": el mensaje presenta datos concretos de cobertura, copago, autorización, red médica, etc. → extrae los campos disponibles
- "general": saludos, aclaraciones generales, alertas de emergencia, preguntas sin datos estructurados

Tipos de cada campo:
- plans: array de strings o null
- specialty: string o null
- estimated_copay: string con el monto (ej: "$20.00 fijo", "20%") o null
- requires_authorization: boolean o null
- waiting_period_days: número entero o null
- network_tier: string o null
- providers: array de strings o null
- annual_deductible: string con el monto (ej: "$100.00") o null
- notes: string con observaciones adicionales o null
- deductible_applies: boolean o null

No inventes datos. Si un campo no aparece en el mensaje, deja null.
Devuelve SOLO el JSON, sin texto adicional."""


def extract_response_structure(reply: str) -> dict:
    """Post-processes the agent text reply to extract structured fields via Gemini."""
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash",
            temperature=0,
            api_key=os.getenv("GEMINI_API_KEY"),
        )
        result = llm.invoke(_PROMPT.format(reply=reply))
        content = result.content if hasattr(result, "content") else str(result)

        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1]) if lines[-1] == "```" else "\n".join(lines[1:])
        content = content.strip()

        data = json.loads(content)

        return {
            "response_type": data.get("response_type", "general"),
            "plans": data.get("plans") or None,
            "specialty": data.get("specialty") or None,
            "estimated_copay": data.get("estimated_copay") or None,
            "requires_authorization": data.get("requires_authorization"),
            "waiting_period_days": data.get("waiting_period_days"),
            "network_tier": data.get("network_tier") or None,
            "providers": data.get("providers") or None,
            "annual_deductible": data.get("annual_deductible") or None,
            "notes": data.get("notes") or None,
            "deductible_applies": data.get("deductible_applies"),
        }

    except Exception as e:
        logger.error(f"extract_response_structure error: {e}", exc_info=True)
        return {"response_type": "general"}
