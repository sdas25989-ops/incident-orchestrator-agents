"""
PriorityAgent — Utility Agent (claude-3-5-haiku)

Evaluates order value + frustration signal.
Sets PCC = CAT A when order_value > $5,000 AND frustration detected.
"""

from clients.servicenow import ServiceNowClient
from models.incident import Incident
from tools.servicenow_tools import (
    TOOL_SN_SET_PCC,
    TOOL_SN_ADD_WORK_NOTE,
    SN_TOOL_HANDLERS,
)
from agents.base_agent import BaseAgent

_SYSTEM_PROMPT = """You are PriorityAgent, a service escalation specialist.

You receive the triage assessment (order_value, has_frustration) for a ServiceNow incident.

Escalation rule — BOTH conditions must be true to escalate:
  1. order_value is strictly greater than 5000 (USD)  [exactly $5000 does NOT qualify]
  2. has_frustration is true

If BOTH conditions are met:
  a. Call sn_set_pcc with sys_id and category="CAT A"
  b. Call sn_add_work_note with an explanation:
     "[PriorityAgent] Escalated to CAT A: order value ${order_value} exceeds $5,000 threshold and customer expressed frustration/dissatisfaction."
  c. Return JSON: {"escalated": true, "pcc": "CAT A", "reason": "<brief>"}

If either condition is NOT met:
  Do NOT call any tool.
  Return JSON: {"escalated": false, "pcc": "unchanged", "reason": "<brief explanation>"}

Return ONLY valid JSON. No markdown, no prose.
"""


class PriorityAgent(BaseAgent):
    model = "claude-3-5-haiku-20241022"
    system_prompt = _SYSTEM_PROMPT
    tools = [TOOL_SN_SET_PCC, TOOL_SN_ADD_WORK_NOTE]

    def __init__(self, sn: ServiceNowClient) -> None:
        super().__init__()
        self._sn = sn

    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> dict:
        handler = SN_TOOL_HANDLERS.get(tool_name)
        if not handler:
            raise ValueError(f"PriorityAgent: unknown tool '{tool_name}'")
        return handler(self._sn, tool_input)

    def run_for_incident(self, incident: Incident, triage_result: dict) -> str:
        order_value = triage_result.get("order_value") or 0
        has_frustration = triage_result.get("has_frustration", False)
        self._log.info(
            "Assessing priority for %s — order_value=%s frustration=%s",
            incident.number, order_value, has_frustration
        )
        return self.run(
            f"Incident Number : {incident.number}\n"
            f"sys_id          : {incident.sys_id}\n"
            f"Order Value (USD): {order_value}\n"
            f"Frustration Detected: {has_frustration}\n\n"
            "Evaluate CAT A escalation criteria and take action if warranted."
        )
