from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class CopayType(str, Enum):
    FIXED = "fixed"
    PERCENTAGE = "percentage"


class NetworkTier(str, Enum):
    PREFERRED = "preferred"
    IN_NETWORK = "in_network"
    OUT_OF_NETWORK = "out_of_network"


class BenefitRule(BaseModel):
    service_name: str
    service_category: str
    copay_type: CopayType
    copay_value: float
    coverage_percentage: float = 80.0
    network_tier: NetworkTier = NetworkTier.IN_NETWORK
    requires_authorization: bool = False
    waiting_period_days: int = 0
    deductible_applies: bool = True
    specialty_aliases: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class InsurancePlan(BaseModel):
    """Schema used with with_structured_output — Gemini extracts this from the PDF."""

    plan_name: str
    insurer_name: str
    annual_deductible: float = 0.0
    deductible_currency: str = "USD"
    benefit_rules: list[BenefitRule]
    providers: list[str] = Field(default_factory=list)
    source_document: Optional[str] = None
    nombre_seguro: str = ""


class InsuranceChunk(BaseModel):
    """Denormalized unit stored in MongoDB: one plan × one rule × one provider."""

    plan_name: str
    insurer_name: str
    nombre_seguro: str
    annual_deductible: float
    service_name: str
    service_category: str
    specialty_aliases: list[str]
    copay_type: str
    copay_value: float
    coverage_percentage: float
    network_tier: str
    requires_authorization: bool
    waiting_period_days: int
    deductible_applies: bool
    provider: Optional[str] = None
    notes: Optional[str] = None
    source_document: Optional[str] = None


class ServiceAliases(BaseModel):
    service_name: str
    aliases: list[str]


class AliasEnrichment(BaseModel):
    """Schema used to enrich extracted rules with patient-friendly search terms."""

    services: list[ServiceAliases]


class NetworkCoverage(BaseModel):
    """One (provider × service) row from a medical network directory.

    Unlike InsuranceChunk, the copay belongs to the specific provider+service
    pair — there is no cartesian product and no plan-level benefit rules.
    """
    nombre_seguro: str = ""
    red: str = ""
    ciudad: str = ""
    provider: str
    address: str = ""
    service_name: str
    service_category: str = ""
    specialty_aliases: list[str] = Field(default_factory=list)
    copay_type: str = "fixed"
    copay_value: float = 0.0
    coverage_percentage: float = 80.0
    requires_authorization: bool = False
    notes: Optional[str] = None
    source_document: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    # Response classification
    response_type: str = "general"  # "plan_selection" | "coverage_info" | "general"
    # plan_selection fields
    plans: Optional[list[str]] = None
    # coverage_info fields
    specialty: Optional[str] = None
    estimated_copay: Optional[str] = None
    requires_authorization: Optional[bool] = None
    waiting_period_days: Optional[int] = None
    network_tier: Optional[str] = None
    providers: Optional[list[str]] = None
    annual_deductible: Optional[str] = None
    notes: Optional[str] = None
    deductible_applies: Optional[bool] = None
