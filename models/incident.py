from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMAssessment:
    """Result of Claude LLM info-quality check."""
    sufficient: bool
    missing_fields: list[str]
    has_frustration: bool
    order_value: Optional[float]
    order_id: Optional[str]


@dataclass
class CancelResult:
    """Result of order cancellation API call."""
    success: bool
    message: str


@dataclass
class Incident:
    """Represents a ServiceNow incident record."""
    sys_id: str
    number: str
    short_description: str
    description: str
    state: str                        # "1"=New, "2"=In Progress, "4"=Pending, "6"=Resolved
    caller_id: str = ""
    assigned_to: str = ""
    assignment_group: str = ""
    reported_ci: str = ""             # cmdb_ci field value (display)
    reported_ci_link: str = ""        # cmdb_ci field link
    pcc: str = ""                     # Problem Correlation Code (PCC) — field name set via SN_PCC_FIELD
    work_notes: str = ""
    close_notes: str = ""

    # Populated during orchestration (not from SN)
    llm_assessment: Optional[LLMAssessment] = field(default=None, repr=False)
    cancel_result: Optional[CancelResult] = field(default=None, repr=False)

    @property
    def order_id(self) -> Optional[str]:
        if self.llm_assessment:
            return self.llm_assessment.order_id
        return None

    @property
    def order_value(self) -> Optional[float]:
        if self.llm_assessment:
            return self.llm_assessment.order_value
        return None
