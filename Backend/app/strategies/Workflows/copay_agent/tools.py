import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from langchain_core.tools import tool

from app.manager.Mongo import Mongo

load_dotenv()
logger = logging.getLogger(__name__)

INSURANCE_COLLECTION = "insurance_rules"
PROVIDERS_COLLECTION = "found_providers"
NETWORK_COLLECTION = "network_directory"

# Cache TTL: re-search Tavily after 7 days for the same specialty+city
CACHE_TTL_DAYS = 7


@tool
def list_available_plans() -> str:
    """
    Returns the list of insurance plans currently loaded in the database.
    Use this tool when the patient has not mentioned their insurance plan name,
    or to verify that a plan the patient mentioned actually exists.
    """
    try:
        db = Mongo.get_instance()
        plans = set()
        for coll_name in (INSURANCE_COLLECTION, NETWORK_COLLECTION):
            plans.update(p for p in db[coll_name].distinct("nombre_seguro") if p)
        if not plans:
            return "No hay ningún plan de seguro cargado en la base de datos todavía."
        plan_list = "\n".join(f"- {p}" for p in sorted(plans))
        return f"Planes disponibles en la base de datos:\n{plan_list}"
    except Exception as e:
        logger.error(f"list_available_plans error: {e}", exc_info=True)
        return f"Error al obtener los planes: {str(e)}"


@tool
def list_available_networks(plan_name: str) -> str:
    """
    Returns the medical networks (redes) available for a given insurance plan.
    A patient belongs to a specific network within their plan, and the copay
    depends on it. Use this after identifying the plan to ask the patient which
    network they belong to.

    Args:
        plan_name: Exact insurance plan identifier (e.g., "CONFIAMED").
    """
    try:
        db = Mongo.get_instance()
        collection = db[NETWORK_COLLECTION]
        networks = [
            n for n in collection.distinct(
                "red", {"nombre_seguro": {"$regex": f"^{plan_name}$", "$options": "i"}}
            ) if n
        ]
        if not networks:
            return f"No hay redes registradas para el plan '{plan_name}'."
        network_list = "\n".join(f"- {n}" for n in sorted(networks))
        return f"Redes disponibles para '{plan_name}':\n{network_list}"
    except Exception as e:
        logger.error(f"list_available_networks error: {e}", exc_info=True)
        return f"Error al obtener las redes: {str(e)}"


@tool
def search_insurance_coverage(plan_name: str, query: str) -> str:
    """
    Searches the insurance rules database for coverage and copay information
    for a specific insurance plan. Always call list_available_plans first if
    you do not know the patient's plan name.

    Args:
        plan_name: Exact insurance plan identifier (e.g., "CONFIPLUS-60K").
                   Must match one of the values returned by list_available_plans.
        query: Description of the medical service or symptom in Spanish
               (e.g., "dolor de rodilla traumatología", "consulta médica general")
    """
    try:
        db = Mongo.get_instance()
        collection = db[INSURANCE_COLLECTION]

        words = [w for w in query.split() if len(w) > 3]
        search_terms = [query] + words if words else [query]

        or_conditions = []
        for term in search_terms:
            or_conditions.extend([
                {"service_name": {"$regex": term, "$options": "i"}},
                {"service_category": {"$regex": term, "$options": "i"}},
                {"specialty_aliases": {"$elemMatch": {"$regex": term, "$options": "i"}}},
            ])

        query_filter = {
            "$and": [
                {"nombre_seguro": {"$regex": f"^{plan_name}$", "$options": "i"}},
                {"$or": or_conditions},
            ]
        }

        results = list(collection.find(query_filter, {"_id": 0}).limit(5))

        if not results:
            plan_exists = collection.count_documents(
                {"nombre_seguro": {"$regex": f"^{plan_name}$", "$options": "i"}}, limit=1
            )
            if plan_exists:
                return (
                    f"El plan '{plan_name}' SÍ existe, pero no tiene una regla de cobertura "
                    f"registrada para '{query}'. NO vuelvas a preguntar por el nombre del plan. "
                    "Continúa con find_network_providers para buscar proveedores de la red "
                    "que cubran este servicio."
                )
            available = [p for p in collection.distinct("nombre_seguro") if p]
            plans_str = "\n".join(f"- {p}" for p in sorted(available)) if available else "ninguno"
            return (
                f"No se encontró el plan '{plan_name}' en la base de datos.\n"
                f"Planes disponibles:\n{plans_str}\n"
                "Pregunta al paciente a cuál de estos planes se refiere."
            )

        formatted = []
        for i, doc in enumerate(results, 1):
            copay_type = doc.get("copay_type", "N/A")
            copay_value = doc.get("copay_value", 0)
            coverage_percentage = doc.get("coverage_percentage", 0)

            if copay_type == "fixed":
                copay_text = f"${copay_value:.2f} fijo"
            elif copay_type == "percentage":
                copay_text = f"{copay_value:.0f}% (seguro paga {coverage_percentage:.0f}%)"
            else:
                copay_text = str(copay_value)

            lines = [
                f"[Resultado {i}]",
                f"Servicio: {doc.get('service_name', 'N/A')}",
                f"Plan: {doc.get('plan_name', 'N/A')} | Aseguradora: {doc.get('insurer_name', 'N/A')}",
                f"Deducible anual del plan: ${doc.get('annual_deductible', 0):.2f}",
                f"Copago del paciente: {copay_text}",
                f"Red médica: {doc.get('network_tier', 'N/A')}",
                f"Requiere autorización previa: {doc.get('requires_authorization', False)}",
                f"Período de espera: {doc.get('waiting_period_days', 0)} días",
                f"Deducible aplica: {doc.get('deductible_applies', True)}",
            ]
            if doc.get("provider"):
                lines.append(f"Proveedor disponible: {doc['provider']}")
            if doc.get("specialty_aliases"):
                lines.append(f"También aplica para: {', '.join(doc['specialty_aliases'])}")
            if doc.get("notes"):
                lines.append(f"Nota: {doc['notes']}")

            formatted.append("\n".join(lines))

        return "\n\n".join(formatted)

    except Exception as e:
        logger.error(f"search_insurance_coverage error: {e}", exc_info=True)
        return f"Error al buscar cobertura: {str(e)}"


@tool
def find_network_providers(plan_name: str, service: str, city: str, red: str = "") -> str:
    """
    Finds in-network hospitals/clinics that cover a medical service in a city,
    sorted by copay (cheapest first). Use this to recommend the most economical
    provider once you know the patient's plan, the service and the city.

    Args:
        plan_name: Exact insurance plan identifier (e.g., "CONFIAMED").
        service: Medical service or specialty in Spanish (e.g., "consulta médica", "laboratorio").
        city: Patient's city in Ecuador (e.g., "Quito", "Guayaquil").
        red: Optional. The patient's specific medical network (e.g., "CONFIRED MASIVA").
             If omitted, returns results from all networks, each labeled with its red.
    """
    try:
        db = Mongo.get_instance()
        collection = db[NETWORK_COLLECTION]

        and_conditions = [
            {"nombre_seguro": {"$regex": f"^{plan_name}$", "$options": "i"}},
            {"ciudad": {"$regex": city, "$options": "i"}},
            {"$or": [
                {"service_name": {"$regex": service, "$options": "i"}},
                {"service_category": {"$regex": service, "$options": "i"}},
                {"specialty_aliases": {"$elemMatch": {"$regex": service, "$options": "i"}}},
            ]},
        ]
        if red:
            and_conditions.append({"red": {"$regex": f"^{red}$", "$options": "i"}})

        results = list(collection.find({"$and": and_conditions}, {"_id": 0}))
        if not results:
            scope = f" en la red '{red}'" if red else ""
            return (
                f"No se encontraron proveedores de '{service}' en {city}{scope} "
                f"para el plan '{plan_name}'."
            )

        # Cheapest first — providers with a $0 / lower copay come first.
        results.sort(key=lambda r: r.get("copay_value", 999999))

        formatted = []
        for i, doc in enumerate(results[:8], 1):
            copay_type = doc.get("copay_type", "N/A")
            copay_value = doc.get("copay_value", 0)
            if copay_type == "fixed":
                copay_text = f"${copay_value:.2f} fijo"
            elif copay_type == "percentage":
                copay_text = f"{copay_value:.0f}% del costo"
            else:
                copay_text = str(copay_value)

            lines = [
                f"[Opción {i}] {doc.get('provider', 'N/A')}",
                f"Servicio: {doc.get('service_name', 'N/A')}",
                f"Copago del paciente: {copay_text}",
                f"Ciudad: {doc.get('ciudad', 'N/A')}",
            ]
            if doc.get("red"):
                lines.append(f"Red: {doc['red']}")
            if doc.get("address"):
                lines.append(f"Dirección: {doc['address']}")
            if doc.get("requires_authorization"):
                lines.append("Requiere autorización previa")
            if doc.get("notes"):
                lines.append(f"Nota: {doc['notes']}")

            formatted.append("\n".join(lines))

        return "\n\n".join(formatted)

    except Exception as e:
        logger.error(f"find_network_providers error: {e}", exc_info=True)
        return f"Error al buscar proveedores de red: {str(e)}"


@tool
def search_providers_online(specialty: str, city: str) -> str:
    """
    Searches online for medical providers (clinics, hospitals, specialists) when the insurance
    database has no coverage rules for the requested service or specialty.
    Use this tool ONLY when search_insurance_coverage returns no results or the specific
    specialist is not found in the insurance database.
    Saves results to MongoDB for future queries (cache TTL: 7 days).

    Args:
        specialty: Medical specialty or service in Spanish (e.g., "cardiología", "dermatólogo")
        city: Patient's city in Ecuador (e.g., "Quito", "Guayaquil", "Cuenca")
    """
    try:
        db = Mongo.get_instance()
        collection = db[PROVIDERS_COLLECTION]

        # Check cache first — avoid burning Tavily API calls for repeated queries
        cutoff = datetime.now(tz=timezone.utc).replace(tzinfo=None)
        from datetime import timedelta
        cutoff -= timedelta(days=CACHE_TTL_DAYS)

        cached = list(
            collection.find(
                {
                    "specialty": {"$regex": specialty, "$options": "i"},
                    "city": {"$regex": city, "$options": "i"},
                    "found_at": {"$gte": cutoff},
                },
                {"_id": 0},
            ).limit(5)
        )

        if cached:
            logger.info(f"Returning cached providers for {specialty} in {city}")
            return _format_providers(cached, from_cache=True)

        # Not cached — call Tavily
        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            return "No se pudo realizar la búsqueda online: TAVILY_API_KEY no configurada."

        from tavily import TavilyClient
        client = TavilyClient(api_key=api_key)

        query = f"{specialty} {city} Ecuador clínica hospital precio consulta"
        logger.info(f"Tavily search: '{query}'")

        response = client.search(
            query=query,
            search_depth="advanced",
            max_results=5,
        )

        results = response.get("results", [])
        if not results:
            return f"No se encontraron proveedores de {specialty} en {city} mediante búsqueda online."

        # Build and persist provider records
        now = datetime.utcnow()
        records = []
        for r in results:
            records.append(
                {
                    "specialty": specialty.lower(),
                    "city": city.lower(),
                    "name": r.get("title", ""),
                    "description": r.get("content", "")[:400],
                    "url": r.get("url", ""),
                    "source": "tavily",
                    "found_at": now,
                }
            )

        collection.insert_many(records)
        # Create index on first insert (no-op if exists)
        collection.create_index([("specialty", 1), ("city", 1)])
        collection.create_index("found_at")

        logger.info(f"Persisted {len(records)} providers for {specialty} in {city}")
        return _format_providers(records, from_cache=False)

    except Exception as e:
        logger.error(f"search_providers_online error: {e}", exc_info=True)
        return f"Error al buscar proveedores online: {str(e)}"


def _format_providers(providers: list, from_cache: bool) -> str:
    header = (
        "(Resultados del caché local)\n\n" if from_cache
        else "(Resultados obtenidos de búsqueda web en tiempo real)\n\n"
    )
    lines = []
    for i, p in enumerate(providers, 1):
        block = [
            f"[Opción {i}] {p.get('name', 'N/A')}",
            f"Descripción: {p.get('description', 'N/A')}",
        ]
        if p.get("url"):
            block.append(f"Más info: {p['url']}")
        lines.append("\n".join(block))
    return header + "\n\n".join(lines)


@tool
def calculate_copay(
    copay_type: str,
    copay_value: float,
    service_cost: float,
    deductible_pending: float,
    coverage_percentage: float,
) -> str:
    """
    Calculates the exact amount a patient must pay for a medical service.

    Args:
        copay_type: 'fixed' (monto fijo) or 'percentage' (porcentaje)
        copay_value: Dollar amount if fixed; patient's percentage if percentage
                     (e.g., 20 means the patient pays 20%, insurance pays 80%)
        service_cost: Total cost of the medical service in USD
        deductible_pending: Remaining annual deductible the patient still owes (0 if fully paid)
        coverage_percentage: Percentage the insurance pays after deductible is met (e.g., 80)

    Returns a detailed cost breakdown showing exactly what the patient pays.

    IMPORTANT: For EMERGENCY services, note that access takes priority over cost.
    """
    try:
        service_cost = float(service_cost)
        deductible_pending = max(0.0, float(deductible_pending))
        copay_value = float(copay_value)
        coverage_percentage = float(coverage_percentage)

        deductible_to_pay = min(deductible_pending, service_cost)
        eligible_amount = max(0.0, service_cost - deductible_to_pay)

        if copay_type == "fixed":
            patient_pays = copay_value + deductible_to_pay
            insurance_pays = max(0.0, eligible_amount - copay_value)
            formula = (
                f"Copago fijo: ${copay_value:.2f} + "
                f"Deducible por pagar: ${deductible_to_pay:.2f} = "
                f"**${patient_pays:.2f}**"
            )
        else:
            patient_share = eligible_amount * (copay_value / 100.0)
            patient_pays = deductible_to_pay + patient_share
            insurance_pays = eligible_amount * (coverage_percentage / 100.0)
            formula = (
                f"Deducible por pagar: ${deductible_to_pay:.2f} + "
                f"{copay_value:.0f}% de ${eligible_amount:.2f} = ${patient_share:.2f} → "
                f"**${patient_pays:.2f}**"
            )

        return (
            f"CÁLCULO DE COPAGO:\n"
            f"Costo total del servicio: ${service_cost:.2f}\n"
            f"Deducible por cubrir: ${deductible_to_pay:.2f}\n"
            f"Monto elegible para cobertura: ${eligible_amount:.2f}\n"
            f"{'─' * 40}\n"
            f"PACIENTE PAGA: ${patient_pays:.2f}\n"
            f"SEGURO PAGA: ${insurance_pays:.2f}\n"
            f"Fórmula: {formula}"
        )

    except Exception as e:
        logger.error(f"calculate_copay error: {e}", exc_info=True)
        return f"Error en el cálculo de copago: {str(e)}"
