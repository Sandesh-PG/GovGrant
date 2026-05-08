"""
GovGrant Pydantic Schemas
These are the canonical data contracts shared across all 4 agents.
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ─── Enums ────────────────────────────────────────────────────────────────────

class Sector(str, Enum):
    AGRICULTURE = "agriculture"
    MANUFACTURING = "manufacturing"
    IT_TECH = "it_tech"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    FOOD_PROCESSING = "food_processing"
    TEXTILE = "textile"
    RENEWABLE_ENERGY = "renewable_energy"
    FINTECH = "fintech"
    RETAIL = "retail"
    LOGISTICS = "logistics"
    OTHER = "other"


class EntityType(str, Enum):
    STARTUP = "startup"
    MSME = "msme"
    PROPRIETORSHIP = "proprietorship"
    PARTNERSHIP = "partnership"
    PRIVATE_LIMITED = "private_limited"
    PUBLIC_LIMITED = "public_limited"
    NGO = "ngo"
    OTHER = "other"


class PurposeType(str, Enum):
    WORKING_CAPITAL = "working_capital"
    CAPEX = "capex"
    R_AND_D = "r_and_d"
    EXPORT = "export"
    HIRING = "hiring"
    TECHNOLOGY_UPGRADE = "technology_upgrade"
    MARKET_EXPANSION = "market_expansion"
    SUSTAINABILITY = "sustainability"
    OTHER = "other"


# ─── Agent 1 Output ───────────────────────────────────────────────────────────

class UserProfile(BaseModel):
    """Structured output from IntakeAgent — contract for downstream agents."""
    session_id: str = Field(..., description="Unique session identifier")
    sector: Sector = Field(..., description="Primary business sector")
    state: str = Field(..., description="Indian state of incorporation")
    annual_revenue_inr: Optional[float] = Field(
        None, description="Annual revenue in INR (0 for pre-revenue startups)"
    )
    entity_type: EntityType = Field(..., description="Legal entity classification")
    team_size: int = Field(..., ge=1, description="Number of full-time employees")
    purpose: PurposeType = Field(..., description="Primary fund-use purpose")
    raw_description: str = Field(
        ..., description="Raw user description for LLM context"
    )
    years_in_operation: Optional[int] = Field(
        None, ge=0, description="Years since incorporation"
    )
    is_women_led: bool = Field(False, description="Is this a women-led enterprise?")
    is_sc_st_led: bool = Field(False, description="SC/ST founder-led enterprise?")
    has_existing_loans: Optional[bool] = Field(None)


# ─── Agent 2 Output ───────────────────────────────────────────────────────────

class Scheme(BaseModel):
    """Raw scheme object returned by ResearchAgent before scoring."""
    scheme_id: str = Field(..., description="Unique identifier (slug)")
    name: str = Field(..., description="Official scheme name")
    ministry: str = Field(..., description="Issuing ministry / authority")
    portal_url: str = Field(..., description="Official application portal URL")
    description: str = Field(..., description="Plain-English summary (≤200 chars)")
    eligible_sectors: List[str] = Field(default_factory=list)
    eligible_entity_types: List[str] = Field(default_factory=list)
    eligible_states: List[str] = Field(
        default_factory=list,
        description="Empty list means pan-India"
    )
    max_revenue_inr: Optional[float] = Field(
        None, description="Revenue cap for eligibility (None = no cap)"
    )
    max_team_size: Optional[int] = Field(None)
    grant_amount_inr: Optional[float] = Field(None, description="Max grant / loan amount")
    deadline: Optional[str] = Field(None, description="Application deadline (ISO date)")
    source: str = Field("rag", description="'rag' | 'web_search'")
    raw_chunk: Optional[str] = Field(None, description="Raw PDF chunk for reference")


# ─── Agent 3 Output ───────────────────────────────────────────────────────────

class ScoreBreakdown(BaseModel):
    eligibility: int = Field(..., ge=0, le=40, description="Hard eligibility score")
    relevance: int = Field(..., ge=0, le=30, description="Sector & purpose relevance")
    benefit: int = Field(..., ge=0, le=20, description="Grant quantum & benefit score")
    ease: int = Field(..., ge=0, le=10, description="Application ease / speed")


class RankedScheme(BaseModel):
    """Validated and scored scheme — output from ValidatorAgent."""
    scheme: Scheme
    composite_score: int = Field(..., ge=0, le=100)
    score_breakdown: ScoreBreakdown
    llm_rationale: str = Field(..., description="1-sentence eligibility rationale")
    rank: int = Field(..., ge=1, le=5)


# ─── Agent 4 Output ───────────────────────────────────────────────────────────

class DocumentItem(BaseModel):
    name: str
    description: str
    is_mandatory: bool = True
    applicable_schemes: List[str] = Field(default_factory=list)


class ActionCard(BaseModel):
    """Per-scheme action card for the planner."""
    scheme_id: str
    scheme_name: str
    portal_url: str
    deadline: Optional[str] = None
    steps: List[str] = Field(..., description="Ordered list of application steps")
    estimated_days: Optional[int] = Field(None, description="Estimated processing time")
    tips: List[str] = Field(default_factory=list)


class GrantReport(BaseModel):
    """Final output from PlannerAgent — everything the frontend needs to render."""
    session_id: str
    user_profile: UserProfile
    top_schemes: List[RankedScheme]
    documents_checklist: List[DocumentItem]
    action_cards: List[ActionCard]
    cover_summary: str = Field(
        ..., description="150-word copy-ready cover summary for applications"
    )
    generated_at: str = Field(..., description="ISO timestamp of report generation")
