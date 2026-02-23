"""
CIValidationAgent — Utility Agent (claude-3-5-haiku)

Validates the Reported CI (cmdb_ci) field.
Non-blocking: pipeline continues regardless of outcome.
"""

from clients.servicenow import ServiceNowClient
from models.incident import Incident
from tools.servicenow_tools import TOOL_SN_ADD_WORK_NOTE, SN_TOOL_HANDLERS
from agents.base_agent import BaseAgent

_SYSTEM_PROMPT = """You are CIValidationAgent, an IT asset management specialist.

Your only task: validate the 'Reported CI' field on a ServiceNow incident.

Decision:
- If reported_ci is non-empty (any non-blank string):
    Do NOT call any tool.
    Return JSON: {"ci_valid": true, "ci_value": "<the value>"}

- If reported_ci is empty, null, or blank:
    Call sn_add_work_note with this exact note:
    "[Orchestrator] Warning: The 'Reported CI' (cmdb_ci) field is empty. Please identify and populate the correct Configuration Item before closing."
    Then return JSON: {"ci_valid": false, "note_added": true}

Return ONLY valid JSON. No markdown, no prose.
"""


class CIValidationAgent(BaseAgent):
    model = "claude-3-5-haiku-20241022"
    system_prompt = _SYSTEM_PROMPT
    tools = [TOOL_SN_ADD_WORK_NOTE]

    def __init__(self, sn: ServiceNowClient) -> None:
        super().__init__()
        self._sn = sn

    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> dict:
        handler = SN_TOOL_HANDLERS.get(tool_name)
        if not handler:
            raise ValueError(f"CIValidationAgent: unknown tool '{tool_name}'")
        return handler(self._sn, tool_input)

    def run_for_incident(self, incident: Incident) -> str:
        self._log.info("Validating CI for incident %s", incident.number)
        return self.run(
            f"Incident Number: {incident.number}\n"
            f"sys_id: {incident.sys_id}\n"
            f"Reported CI (cmdb_ci): '{incident.reported_ci}'\n\n"
            "Validate the Reported CI field and take the appropriate action."
        )
