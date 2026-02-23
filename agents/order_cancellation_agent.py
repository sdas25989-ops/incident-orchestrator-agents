"""
OrderCancellationAgent — Utility Agent (claude-3-5-haiku)

Cancels the order referenced in the incident via Order Management API.
Adds a work note with the outcome regardless of success or failure.
"""

from typing import Optional

from clients.order_api import OrderAPIClient
from clients.servicenow import ServiceNowClient
from models.incident import Incident
from tools.order_tools import TOOL_CANCEL_ORDER, ORDER_TOOL_HANDLERS
from tools.servicenow_tools import TOOL_SN_ADD_WORK_NOTE, SN_TOOL_HANDLERS
from agents.base_agent import BaseAgent

_SYSTEM_PROMPT = """You are OrderCancellationAgent, an order management specialist.

Your task: cancel the customer's order and record the outcome as a work note.

Steps:
1. Check the order_id you received.

2a. If order_id is null, empty, or "NOT FOUND":
    - Call sn_add_work_note:
      "[OrderCancellationAgent] No order ID found in incident description. Manual cancellation required."
    - Return JSON: {"success": false, "order_id": null, "message": "No order ID found in description."}

2b. If order_id is present:
    - Call cancel_order with the order_id.
    - Then call sn_add_work_note with the outcome:
      "[OrderCancellationAgent] Order cancellation result for <order_id>: <success/failure> — <api_message>"
    - Return JSON: {"success": <bool>, "order_id": "<id>", "message": "<api_message>"}

Always call sn_add_work_note after attempting cancellation (or when no order ID found).
Return ONLY valid JSON. No markdown, no prose.
"""


class OrderCancellationAgent(BaseAgent):
    model = "claude-3-5-haiku-20241022"
    system_prompt = _SYSTEM_PROMPT
    tools = [TOOL_CANCEL_ORDER, TOOL_SN_ADD_WORK_NOTE]

    def __init__(self, sn: ServiceNowClient, order_api: OrderAPIClient) -> None:
        super().__init__()
        self._sn = sn
        self._order_api = order_api

    def _handle_tool_call(self, tool_name: str, tool_input: dict) -> dict:
        if tool_name == "cancel_order":
            return ORDER_TOOL_HANDLERS["cancel_order"](self._order_api, tool_input)
        handler = SN_TOOL_HANDLERS.get(tool_name)
        if not handler:
            raise ValueError(f"OrderCancellationAgent: unknown tool '{tool_name}'")
        return handler(self._sn, tool_input)

    def run_for_incident(self, incident: Incident, order_id: Optional[str]) -> str:
        self._log.info(
            "Processing order cancellation for %s (order_id=%s)",
            incident.number, order_id
        )
        return self.run(
            f"Incident Number: {incident.number}\n"
            f"sys_id: {incident.sys_id}\n"
            f"Order ID to cancel: {order_id or 'NOT FOUND'}\n\n"
            "Cancel the order if an ID is present, then add a work note with the result."
        )
