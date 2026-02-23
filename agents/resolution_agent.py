"""
ResolutionAgent — Sub-Agent (claude-3-5-sonnet)

Composes structured resolution notes from all previous agent results
and resolves the incident. This is always the final step.
"""

from clients.servicenow import ServiceNowClient
from models.incident import Incident
from tools.servicenow_tools import TOOL_SN_RESOLVE_INCIDENT, SN_TOOL_HANDLERS
from agents.base_agent import BaseAgent

_SYSTEM_PROMPT = """You are ResolutionAgent, an expert IT incident closer.

You receive the incident details and a full orchestration summary from all prior agents.
Your job: write clear structured resolution notes, then resolve the incident.

Resolution notes MUST follow this exact template (fill each section):
  Issue: <one sentence describing what the user reported — paraphrase the short description>
  Error: <the specific problem identified, or the cancel API result, or "N/A" if none>
  Recovery steps: <what was done — include order cancellation outcome, PCC escalation if any, and CI status>

Guidelines:
- Issue: paraphrase naturally, do not copy verbatim.
- Error: if order cancellation occurred, mention the API response. If no error, write "N/A".
- Recovery steps: be concise but complete. Mention each outcome (order cancelled / not found,
  CAT A escalated / not escalated, CI validated / empty).

Action:
1. Compose the close_notes text following the template above.
2. Call sn_resolve_incident with sys_id and your close_notes.
3. Return ONLY this JSON (no markdown, no prose):
   {"resolved": true, "close_notes": "<the notes you wrote>"}
"""


class ResolutionAgent(BaseAgent):
    model = "claude-3-5-sonnet-20241022"
    system_prompt = _SYSTEM_PROMPT
    tools = [TOOL_SN_RESOLVE_INCIDENT]

    def __init__(self, sn: ServiceNowClient) -> None:
        super().__init__()
        self._sn = sn

    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> dict:
        handler = SN_TOOL_HANDLERS.get(tool_name)
        if not handler:
            raise ValueError(f"ResolutionAgent: unknown tool '{tool_name}'")
        return handler(self._sn, tool_input)

    def run_for_incident(
        self,
        incident: Incident,
        triage_result: dict,
        ci_result: dict,
        priority_result: dict,
        cancel_result: dict,
    ) -> str:
        self._log.info("Resolving incident %s", incident.number)
        return self.run(
            f"Incident Number  : {incident.number}\n"
            f"sys_id           : {incident.sys_id}\n"
            f"Short Description: {incident.short_description}\n\n"
            f"=== Orchestration Summary ===\n"
            f"Triage Result    : {triage_result}\n"
            f"CI Validation    : {ci_result}\n"
            f"Priority Result  : {priority_result}\n"
            f"Cancel Result    : {cancel_result}\n\n"
            "Compose structured resolution notes and resolve this incident."
        )
