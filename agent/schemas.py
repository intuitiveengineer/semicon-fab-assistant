"""Output schema for the maintenance agent.

Diagnosis is the single structured answer the agent returns for every query.
It is enforced via OpenAI structured outputs so the LLM cannot return
free-form text — the response is always valid JSON matching this shape.

The schema is also what the eval benchmark scores against: citations are
checked for recall, likely_causes are checked against ground-truth signatures.
"""

from pydantic import BaseModel, Field


class Cause(BaseModel):
    cause: str = Field(description="Description of the likely root cause.")
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence that this is the actual cause (0.0–1.0).",
    )
    evidence_doc_ids: list[str] = Field(
        description="doc_ids of the retrieved documents that support this cause."
    )


class Diagnosis(BaseModel):
    summary: str = Field(
        description=(
            "One or two sentence summary of the most likely fault and "
            "recommended immediate action."
        )
    )
    likely_causes: list[Cause] = Field(
        description="Ranked list of likely root causes, most confident first."
    )
    recommended_checks: list[str] = Field(
        description="Ordered list of next diagnostic or corrective steps."
    )
    citations: list[str] = Field(
        description="All doc_ids consulted when forming this diagnosis."
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Overall confidence in the diagnosis (0.0–1.0).",
    )
