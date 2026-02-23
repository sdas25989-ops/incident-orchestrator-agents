"""
TriageAgent — Utility Agent (claude-3-5-sonnet)

Responsibilities:
  • Assess incident information quality via native LLM reasoning
  • Extract order_id, order_value, frustration signals from description
  • Assign incident In-Progress OR set to Pending with missing field list
"""

from clients.servicenow import ServiceNowClient
from models.incident import Incident
from tools.servicenow_tools import (
    TOOL_SN_ASSIGN_INCIDENT,
    TOOL_SN_SET_PENDING,
    SN_TOOL_HANDLERS,
)
from agents.base_agent import BaseAgent

_SYSTEM_PROMPT = """You are TriageAgent, an expert IT service desk analyst.

For each incident you receive, do the following in order:

1. READ the incident details carefully — short description and full description.

2. ASSESS information quality. The incident is SUFFICIENT if:
   - It is clear what the user wants (e.g., cancel an order, fix an error)
   - Some identifier is present (order number, ticket ID, account number, etc.)
   - The system or process affected can be identified
   The incident is INSUFFICIENT if critical context is completely missing.

3. EXTRACT from the description (use null if not found):
   - order_id  : any order identifier (e.g. "ORD-12345", "order #9876", "#4401")
   - order_value: numeric dollar amount (e.g. "$6,200" → 6200.0, "5200 USD" → 5200.0)
   - has_frustration: true if description contains strong negative sentiment such as
     "unacceptable", "frustrated", "disappointed", "terrible", "urgent", "angry",
     "not happy", "very unhappy", "cannot believe", "disgraceful", etc.

4. TAKE exactly one terminal ServiceNow action:
   - If SUFFICIENT → call sn_assign_incident to claim the ticket In-Progress.
   - If INSUFFICIENT → call sn_set_pending with a precise list of what is missing.

5. After the tool call completes, return ONLY this JSON (no markdown, no prose):
{
  "action": "assigned" | "pending",
  "order_id": "<string or null>",
  "order_value": <number or null>,
  "has_frustration": <true|false>,
  "missing_fields": ["<field>", ...],
  "reasoning": "<one sentence explaining your decision>"
}

Rules:
- You MUST call a tool before returning your JSON response.
- missing_fields must be empty [] when action is "assigned".
- Be specific in missing_fields: e.g. "order number", "error message", "affected system".
"""


class TriageAgent(BaseAgent):
    model = "claude-3-5-sonnet-20241022"
    system_prompt = _SYSTEM_PROMPT
    tools = [TOOL_SN_ASSIGN_INCIDENT, TOOL_SN_SET_PENDING]

    def __init__(self, sn: ServiceNowClient) -> None:
        super().__init__()
        self._sn = sn

    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> dict:
        handler = SN_TOOL_HANDLERS.get(tool_name)
        if not handler:
            raise ValueError(f"TriageAgent: unknown tool '{tool_name}'")
        return handler(self._sn, tool_input)

    def run_for_incident(self, incident: Incident) -> str:
        self._log.info("Triaging incident %s", incident.number)
        return self.run(
            f"Incident Number : {incident.number}\n"
            f"sys_id          : {incident.sys_id}\n"
            f"Short Description: {incident.short_description}\n\n"
            f"Full Description:\n{incident.description or '(no description provided)'}"
        )
