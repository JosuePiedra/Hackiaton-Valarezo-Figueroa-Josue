import os
import json
import logging
from typing import Optional

from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

from app.models.insurance import (
    AliasEnrichment,
    InsuranceChunk,
    InsurancePlan,
    NetworkCoverage,
)
from app.services.mistral_ocr import MistralOcrService
from app.services.gemini_ocr import GeminiOcrService
from app.services.excel_parser import parse_excel_to_markdown, parse_excel_network_directory
from app.utils.text_splitter import split_text
from app.manager.Mongo import Mongo

load_dotenv()
logger = logging.getLogger(__name__)

INSURANCE_COLLECTION = "insurance_rules"
NETWORK_COLLECTION = "network_directory"

# A document longer than this is split and extracted segment by segment (map-reduce).
SEGMENT_SIZE = 12000
SEGMENT_OVERLAP = 1000

EXTRACTION_SYSTEM_PROMPT = """
Eres un experto en análisis de pólizas de seguros de salud en Ecuador.
Se te proporcionará texto extraído de un documento de seguro médico (en formato markdown).
Tu tarea es extraer TODA la información de cobertura y copagos en formato JSON estructurado.

CONCEPTOS CLAVE:
- Copago: lo que paga el paciente (monto fijo en USD o porcentaje)
- Deducible: monto que el paciente paga primero antes de que el seguro cubra (generalmente anual)
- Porcentaje de cobertura: lo que paga el SEGURO después del deducible

REGLAS DE EXTRACCIÓN:
1. copay_type="fixed" → copay_value es el monto fijo en USD que paga el paciente
2. copay_type="percentage" → copay_value es el porcentaje que paga el PACIENTE (ej: 20 si el seguro paga 80%)
3. coverage_percentage es lo que paga el SEGURO (ej: 80.0 si el seguro paga 80%)
4. specialty_aliases: sinónimos, especialidades médicas o síntomas relacionados con el servicio
5. providers: nombres exactos de clínicas, hospitales o centros de la red médica
6. waiting_period_days=0 si no se menciona período de espera
7. Si no hay información de red, usar network_tier="in_network"
8. Extrae TODAS las reglas de cobertura que encuentres en el documento
9. Este texto puede ser solo un FRAGMENTO del documento. Si el nombre del plan o
   la aseguradora no aparecen en este fragmento, deja plan_name e insurer_name vacíos ("").
   NO inventes nombres.

Responde ÚNICAMENTE con el JSON estructurado de InsurancePlan, sin texto adicional.
"""

ENRICHMENT_SYSTEM_PROMPT = """
Eres un experto en terminología médica en Ecuador.
Para cada servicio médico de un seguro, genera entre 4 y 8 términos que un PACIENTE
real usaría para describir o buscar ese servicio: síntomas comunes, nombres coloquiales,
especialidades médicas relacionadas y partes del cuerpo involucradas.

Ejemplo:
- "Consultas en Pediatría" → ["pediatra", "niños", "control infantil", "doctor de niños", "salud infantil"]
- "Cirugía de rodilla" → ["dolor de rodilla", "traumatología", "operación rodilla", "lesión rodilla", "menisco"]

Responde ÚNICAMENTE con el JSON estructurado de AliasEnrichment.
"""

def _build_ocr_service():
    """Returns Mistral OCR if USE_MISTRAL_OCR=true, otherwise Gemini Vision."""
    use_mistral = os.getenv("USE_MISTRAL_OCR", "false").lower() == "true"
    if use_mistral:
        logger.info("OCR backend: Mistral")
        return MistralOcrService()
    logger.info("OCR backend: Gemini Vision")
    return GeminiOcrService()


class InsuranceExtractionService:

    def __init__(self):
        self.ocr = _build_ocr_service()
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0,
            api_key=os.getenv("GEMINI_API_KEY"),
        )
        self._indexes_created = False
        self._network_indexes_created = False

    def _ensure_indexes(self, collection):
        if self._indexes_created:
            return
        collection.create_index("service_category")
        collection.create_index("plan_name")
        collection.create_index("nombre_seguro")
        collection.create_index([("service_name", 1)])
        self._indexes_created = True

    def _ensure_network_indexes(self, collection):
        if self._network_indexes_created:
            return
        collection.create_index("nombre_seguro")
        collection.create_index("red")
        collection.create_index("ciudad")
        collection.create_index("service_name")
        collection.create_index("provider")
        self._network_indexes_created = True

    def _to_markdown(self, content: bytes, filename: str) -> str:
        """Converts a PDF (via OCR) or Excel file to markdown text."""
        ext = filename.rsplit(".", 1)[-1].lower()
        if ext == "xlsx":
            markdown = parse_excel_to_markdown(content)
            logger.info(f"Excel parsed: {len(markdown)} chars extracted")
        else:
            markdown = self.ocr.process_pdf(content)
            if not markdown:
                raise ValueError(f"OCR returned empty content for {filename}")
            logger.info(f"OCR complete: {len(markdown)} chars extracted")
        logger.info(f"Content preview (first 500 chars): {markdown[:500]!r}")
        return markdown

    async def process_pdf(self, pdf_content: bytes, filename: str, nombre_seguro: str) -> dict:
        logger.info(f"Starting insurance document processing: {filename}")
        markdown = self._to_markdown(pdf_content, filename)

        plan = self._extract_plan(markdown, filename)
        plan = self._enrich_aliases(plan)
        plan.nombre_seguro = nombre_seguro
        logger.info(
            f"Extracted plan '{plan.plan_name}' with "
            f"{len(plan.benefit_rules)} rules and {len(plan.providers)} providers"
        )

        chunks = self._build_chunks(plan)
        logger.info(f"Generated {len(chunks)} denormalized chunks")

        records = [chunk.model_dump() for chunk in chunks]
        if not records:
            raise ValueError(
                f"No se extrajo ninguna regla de cobertura de '{filename}'. "
                f"El OCR produjo {len(markdown)} caracteres. "
                "Verifica que el documento contenga texto legible y tablas de cobertura."
            )

        db = Mongo.get_instance()
        collection = db[INSURANCE_COLLECTION]
        self._ensure_indexes(collection)

        result = collection.insert_many(records)

        return {
            "status": "success",
            "nombre_seguro": nombre_seguro,
            "plan_name": plan.plan_name,
            "insurer_name": plan.insurer_name,
            "benefit_rules_found": len(plan.benefit_rules),
            "providers_found": len(plan.providers),
            "chunks_inserted": len(result.inserted_ids),
        }

    async def process_network_directory(
        self, content: bytes, filename: str, nombre_seguro: str
    ) -> dict:
        """Processes a medical network directory Excel (provider × service rows).

        Uses a deterministic parser — no LLM — since the spreadsheet is already
        a structured table with fixed columns.
        """
        logger.info(f"Starting network directory processing: {filename}")
        if not filename.lower().endswith(".xlsx"):
            raise ValueError("El directorio de red debe ser un archivo Excel (.xlsx)")

        records = parse_excel_network_directory(content)
        if not records:
            raise ValueError(
                f"No se extrajo ningún registro de red de '{filename}'. "
                "Verifica que el Excel tenga columnas de proveedor y servicio."
            )

        records = self._enrich_network_aliases(records)
        for r in records:
            r.nombre_seguro = nombre_seguro
            r.source_document = filename

        db = Mongo.get_instance()
        collection = db[NETWORK_COLLECTION]
        self._ensure_network_indexes(collection)

        result = collection.insert_many([r.model_dump() for r in records])
        cities = sorted({r.ciudad for r in records if r.ciudad})
        providers = sorted({r.provider for r in records if r.provider})
        logger.info(
            f"Network directory stored: {len(records)} records, "
            f"{len(providers)} providers, {len(cities)} cities"
        )
        return {
            "status": "success",
            "nombre_seguro": nombre_seguro,
            "records_inserted": len(result.inserted_ids),
            "providers_found": len(providers),
            "cities_found": len(cities),
        }

    def _extract_plan(self, markdown: str, filename: str) -> InsurancePlan:
        """Extracts a plan. Short documents in one call, long ones via map-reduce."""
        if len(markdown) <= SEGMENT_SIZE:
            plan = self._extract_segment(markdown, filename)
            plan.source_document = filename
            return plan
        return self._extract_map_reduce(markdown, filename)

    def _extract_map_reduce(self, markdown: str, filename: str) -> InsurancePlan:
        segments = split_text(markdown, SEGMENT_SIZE, SEGMENT_OVERLAP)
        logger.info(f"Document split into {len(segments)} segments for extraction")

        partial_plans: list[InsurancePlan] = []
        for i, segment in enumerate(segments, 1):
            try:
                partial = self._extract_segment(segment, f"{filename} (parte {i}/{len(segments)})")
                logger.info(f"Segment {i}: {len(partial.benefit_rules)} rules extracted")
                partial_plans.append(partial)
            except Exception as e:
                logger.error(f"Segment {i} extraction failed: {e}")

        return self._merge_plans(partial_plans, filename)

    def _merge_plans(self, plans: list[InsurancePlan], filename: str) -> InsurancePlan:
        if not plans:
            raise ValueError(f"No se pudo extraer ninguna regla de {filename}")

        plan_name = next(
            (p.plan_name for p in plans if p.plan_name and p.plan_name.strip()), ""
        )
        insurer_name = next(
            (p.insurer_name for p in plans if p.insurer_name and p.insurer_name.strip()), ""
        )
        annual_deductible = next(
            (p.annual_deductible for p in plans if p.annual_deductible > 0), 0.0
        )

        seen_rules = set()
        merged_rules = []
        for p in plans:
            for rule in p.benefit_rules:
                key = rule.service_name.strip().lower()
                if key and key not in seen_rules:
                    seen_rules.add(key)
                    merged_rules.append(rule)

        seen_providers = set()
        merged_providers = []
        for p in plans:
            for provider in p.providers:
                key = provider.strip().lower()
                if key and key not in seen_providers:
                    seen_providers.add(key)
                    merged_providers.append(provider)

        logger.info(
            f"Merged {len(plans)} segments → {len(merged_rules)} unique rules, "
            f"{len(merged_providers)} providers"
        )
        return InsurancePlan(
            plan_name=plan_name or "Plan sin nombre",
            insurer_name=insurer_name or "Aseguradora desconocida",
            annual_deductible=annual_deductible,
            benefit_rules=merged_rules,
            providers=merged_providers,
            source_document=filename,
        )

    def _extract_segment(self, text: str, label: str) -> InsurancePlan:
        structured_llm = self.llm.with_structured_output(InsurancePlan)
        messages = [
            ("system", EXTRACTION_SYSTEM_PROMPT),
            ("human", f"Documento: {label}\n\nContenido extraído:\n{text}"),
        ]
        try:
            return structured_llm.invoke(messages)
        except Exception as e:
            logger.error(f"Structured extraction failed for {label}: {e}. Trying JSON fallback.")
            return self._extract_segment_json_fallback(text, label)

    def _extract_segment_json_fallback(self, text: str, label: str) -> InsurancePlan:
        messages = [
            (
                "system",
                EXTRACTION_SYSTEM_PROMPT
                + "\n\nDevuelve el JSON completo del objeto InsurancePlan.",
            ),
            ("human", f"Documento: {label}\n\n{text}"),
        ]
        response = self.llm.invoke(messages)
        raw = response.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        data = json.loads(raw.strip())
        return InsurancePlan(**data)

    def _enrich_aliases(self, plan: InsurancePlan) -> InsurancePlan:
        """Fills specialty_aliases for rules that came back without them."""
        rules_to_enrich = [r for r in plan.benefit_rules if not r.specialty_aliases]
        if not rules_to_enrich:
            return plan

        service_names = [r.service_name for r in rules_to_enrich]
        structured_llm = self.llm.with_structured_output(AliasEnrichment)
        messages = [
            ("system", ENRICHMENT_SYSTEM_PROMPT),
            (
                "human",
                "Genera términos de búsqueda para estos servicios médicos:\n"
                + "\n".join(f"- {s}" for s in service_names),
            ),
        ]
        try:
            result: AliasEnrichment = structured_llm.invoke(messages)
            alias_map = {
                s.service_name.strip().lower(): s.aliases for s in result.services
            }
            enriched = 0
            for rule in plan.benefit_rules:
                if not rule.specialty_aliases:
                    aliases = alias_map.get(rule.service_name.strip().lower())
                    if aliases:
                        rule.specialty_aliases = aliases
                        enriched += 1
            logger.info(f"Alias enrichment: filled {enriched}/{len(rules_to_enrich)} rules")
        except Exception as e:
            logger.error(f"Alias enrichment failed: {e}")
        return plan

    def _enrich_network_aliases(self, records: list[NetworkCoverage]) -> list[NetworkCoverage]:
        """Fills specialty_aliases on network records.

        One LLM call for the whole file: the unique service names (a small,
        bounded set) are enriched once and the aliases mapped back to every row.
        """
        unique_services = sorted({r.service_name.strip() for r in records if r.service_name})
        if not unique_services:
            return records

        structured_llm = self.llm.with_structured_output(AliasEnrichment)
        messages = [
            ("system", ENRICHMENT_SYSTEM_PROMPT),
            (
                "human",
                "Genera términos de búsqueda para estos servicios médicos:\n"
                + "\n".join(f"- {s}" for s in unique_services),
            ),
        ]
        try:
            result: AliasEnrichment = structured_llm.invoke(messages)
            alias_map = {
                s.service_name.strip().lower(): s.aliases for s in result.services
            }
            enriched = 0
            for r in records:
                aliases = alias_map.get(r.service_name.strip().lower())
                if aliases:
                    r.specialty_aliases = aliases
                    enriched += 1
            logger.info(
                f"Network alias enrichment: {len(unique_services)} unique services, "
                f"{enriched}/{len(records)} records enriched"
            )
        except Exception as e:
            logger.error(f"Network alias enrichment failed: {e}")
        return records

    def _build_chunks(self, plan: InsurancePlan) -> list[InsuranceChunk]:
        providers: list[Optional[str]] = plan.providers if plan.providers else [None]
        chunks = []
        for rule in plan.benefit_rules:
            for provider in providers:
                chunks.append(
                    InsuranceChunk(
                        plan_name=plan.plan_name,
                        insurer_name=plan.insurer_name,
                        nombre_seguro=plan.nombre_seguro,
                        annual_deductible=plan.annual_deductible,
                        service_name=rule.service_name,
                        service_category=rule.service_category,
                        specialty_aliases=rule.specialty_aliases,
                        copay_type=rule.copay_type.value,
                        copay_value=rule.copay_value,
                        coverage_percentage=rule.coverage_percentage,
                        network_tier=rule.network_tier.value,
                        requires_authorization=rule.requires_authorization,
                        waiting_period_days=rule.waiting_period_days,
                        deductible_applies=rule.deductible_applies,
                        provider=provider,
                        notes=rule.notes,
                        source_document=plan.source_document,
                    )
                )
        return chunks
