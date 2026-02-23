"""
LLM Client — Claude API wrapper for incident information quality assessment.

NOTE: In the multi-agent edition this client is kept for API compatibility.
      The TriageAgent now performs the same assessment natively as part of its
      agentic loop, making direct calls to this client unnecessary.
      It is preserved so existing code that imports LLMClient continues to work.

Direct usage (standalone / testing):
    client = LLMClient()
    result = client.assess_info_quality(incident)
    # result.sufficient, result.missing_fields, result.has_frustration,
    # result.order_value, result.order_id
"""

import json
import re

import anthropic

from config.settings import settings
from models.incident import LLMAssessment
from utils.logger import get_logger

log = get_logger(__name__)

_SYSTEM_PROMPT = """You are an expert IT service-desk analyst.
Assess the quality of the provided incident and extract key fields.

Return ONLY valid JSON in exactly this shape — no markdown, no prose:
{
  "sufficient": <true|false>,
  "missing_fields": ["<field>", ...],
  "has_frustration": <true|false>,
  "order_value": <number or null>,
  "order_id": "<string or null>"
}

Rules:
- sufficient=true when: the intent is clear, some identifier is present, the affected
  system/process can be identified.
- missing_fields: list the specific things that are absent when sufficient=false.
  Empty [] when sufficient=true.
- has_frustration=true if the text contains strong negative emotion such as
  "frustrated", "unacceptable", "terrible", "angry", "disgraceful", etc.
- order_value: extract the numeric dollar value (e.g. "$6,200" → 6200.0). null if not found.
- order_id: any order identifier (e.g. "ORD-12345", "#9876"). null if not found.
"""


class LLMClient:
    """
    Wraps the Anthropic Messages API for incident quality assessment.
    Returns an LLMAssessment dataclass populated from Claude's JSON response.
    """

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        log.debug("LLMClient initialised (model=claude-3-5-haiku-20241022)")

    def assess_info_quality(self, incident) -> LLMAssessment:
        """
        Ask Claude to assess the completeness and content of an incident.

        Parameters
        ----------
        incident : Incident
            The incident to assess (uses short_description + description).

        Returns
        -------
        LLMAssessment
            Structured result with sufficient flag, missing fields, frustration
            detection, order value, and order ID.
        """
        user_msg = (
            f"Incident Number: {incident.number}\n"
            f"Short Description: {incident.short_description}\n\n"
            f"Full Description:\n{incident.description or '(no description provided)'}"
        )

        try:
            response = self._client.messages.create(
                model="claude-3-5-haiku-20241022",
                max_tokens=512,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )

            raw = response.content[0].text.strip()
            # Strip markdown code fences if present
            cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
            data = json.loads(cleaned)

            result = LLMAssessment(
                sufficient=bool(data.get("sufficient", False)),
                missing_fields=data.get("missing_fields") or [],
                has_frustration=bool(data.get("has_frustration", False)),
                order_value=data.get("order_value"),
                order_id=data.get("order_id"),
            )
            log.debug(
                "[%s] LLM assessment → sufficient=%s  frustration=%s  order_value=%s  order_id=%s",
                incident.number,
                result.sufficient,
                result.has_frustration,
                result.order_value,
                result.order_id,
            )
            return result

        except json.JSONDecodeError as exc:
            log.error(
                "LLMClient: Failed to parse JSON from Claude response for %s. "
                "Raw: %s. Error: %s",
                incident.number, raw[:200], exc,
            )
            # Fail-safe: treat as sufficient to avoid blocking incident flow
            return LLMAssessment(
                sufficient=True,
                missing_fields=[],
                has_frustration=False,
                order_value=None,
                order_id=None,
            )

        except Exception as exc:
            log.error(
                "LLMClient: Unexpected error assessing incident %s: %s",
                incident.number, exc,
            )
            return LLMAssessment(
                sufficient=True,
                missing_fields=[],
                has_frustration=False,
                order_value=None,
                order_id=None,
            )
