"""
SuperOrchestratorAgent — Master Coordinator (claude-opus-4-5)

Orchestrates the full incident lifecycle by treating each specialist
sub-agent as a callable tool. Claude decides the execution order
dynamically based on each agent's result.

Agent hierarchy:
  SuperOrchestratorAgent (claude-opus-4-5)         ← this file
    ├── TriageAgent          (claude-3-5-sonnet)    ← tool: run_triage
    ├── CIValidationAgent    (claude-3-5-haiku)     ← tool: run_ci_validation
    ├── PriorityAgent        (claude-3-5-haiku)     ← tool: run_priority_assessment
    ├── OrderCancellationAgent (claude-3-5-haiku)   ← tool: run_order_cancellation
    └── ResolutionAgent      (claude-3-5-sonnet)    ← tool: run_resolution
"""

import json
import re
from typing import Any

import anthropic

from agents.ci_validation_agent import CIValidationAgent
from agents.order_cancellation_agent import OrderCancellationAgent
from agents.priority_agent import PriorityAgent
from agents.resolution_agent import ResolutionAgent
from agents.triage_agent import TriageAgent
from clients.order_api import OrderAPIClient
from clients.servicenow import ServiceNowClient
from config.settings import settings
from models.incident import Incident
from utils.logger import get_logger

log = get_logger(__name__)

MAX_ORCHESTRATOR_ITERATIONS = 15

# ── Sub-agent tool definitions (what the SuperOrchestrator sees) ──────────────

_TOOLS = [
    {
        "name": "run_triage",
        "description": (
            "Invoke TriageAgent on an incident. The agent assesses information quality, "
            "extracts order_id/order_value/frustration, and either assigns the incident "
            "In-Progress or sets it to Pending.\n"
            "IMPORTANT: Call this FIRST. If result.action == 'pending' → STOP, do not call any more agents."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sys_id":            {"type": "string",  "description": "Incident sys_id"},
                "incident_number":   {"type": "string",  "description": "e.g. INC0001234"},
                "short_description": {"type": "string",  "description": "Incident short description"},
                "description":       {"type": "string",  "description": "Full incident description body"},
            },
            "required": ["sys_id", "incident_number", "short_description", "description"]
        }
    },
    {
        "name": "run_ci_validation",
        "description": (
            "Invoke CIValidationAgent to verify the Reported CI field. "
            "Adds a work note if CI is empty. Non-blocking — always continue after this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sys_id":          {"type": "string", "description": "Incident sys_id"},
                "incident_number": {"type": "string", "description": "Incident number"},
                "reported_ci":     {"type": "string", "description": "Current cmdb_ci value (empty string if not set)"},
            },
            "required": ["sys_id", "incident_number", "reported_ci"]
        }
    },
    {
        "name": "run_priority_assessment",
        "description": (
            "Invoke PriorityAgent. Sets PCC=CAT A when order_value > $5000 AND has_frustration=true. "
            "Non-blocking — always continue after this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sys_id":          {"type": "string",  "description": "Incident sys_id"},
                "incident_number": {"type": "string",  "description": "Incident number"},
                "order_value":     {"type": "number",  "description": "Order value in USD from triage. Pass 0 if null."},
                "has_frustration": {"type": "boolean", "description": "Frustration flag from triage result"},
            },
            "required": ["sys_id", "incident_number", "order_value", "has_frustration"]
        }
    },
    {
        "name": "run_order_cancellation",
        "description": (
            "Invoke OrderCancellationAgent to cancel the order via the Order Management API. "
            "Adds a work note with the outcome. Non-blocking — always continue after this."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sys_id":          {"type": "string", "description": "Incident sys_id"},
                "incident_number": {"type": "string", "description": "Incident number"},
                "order_id":        {"type": "string", "description": "Order ID from triage result (null if not found)"},
            },
            "required": ["sys_id", "incident_number"]
        }
    },
    {
        "name": "run_resolution",
        "description": (
            "Invoke ResolutionAgent to compose structured resolution notes and resolve the incident. "
            "Always the LAST step. Pass all previous agent results for context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sys_id":            {"type": "string", "description": "Incident sys_id"},
                "incident_number":   {"type": "string", "description": "Incident number"},
                "short_description": {"type": "string", "description": "Incident short description"},
                "triage_result":     {"type": "object", "description": "Full JSON result from run_triage"},
                "ci_result":         {"type": "object", "description": "Full JSON result from run_ci_validation"},
                "priority_result":   {"type": "object", "description": "Full JSON result from run_priority_assessment"},
                "cancel_result":     {"type": "object", "description": "Full JSON result from run_order_cancellation"},
            },
            "required": ["sys_id", "incident_number", "short_description",
                         "triage_result", "ci_result", "priority_result", "cancel_result"]
        }
    },
]

_SYSTEM_PROMPT = """You are SuperOrchestratorAgent, the master coordinator for ServiceNow incident management.

You orchestrate the full incident lifecycle by calling specialist sub-agents as tools.
Each tool invokes a dedicated Claude-powered agent that takes ServiceNow actions autonomously.

═══ MANDATORY EXECUTION SEQUENCE ════════════════════════════════════════

Step 1 — TRIAGE (always first):
  → Call run_triage with incident details.
  → If result.action == "pending": STOP. Do not call any more agents.
    The incident is awaiting information. Return final summary with outcome="pending".
  → If result.action == "assigned": continue to Step 2.

Step 2 — CI VALIDATION (non-blocking):
  → Call run_ci_validation with sys_id, incident_number, and reported_ci.
  → Always continue to Step 3 regardless of result.

Step 3 — PRIORITY ASSESSMENT (non-blocking):
  → Call run_priority_assessment with order_value and has_frustration from triage result.
  → Always continue to Step 4 regardless of result.

Step 4 — ORDER CANCELLATION (non-blocking):
  → Call run_order_cancellation with order_id from triage result (pass null if not found).
  → Always continue to Step 5 regardless of success/failure.

Step 5 — RESOLUTION (always last, only if triage action was "assigned"):
  → Call run_resolution with sys_id, short_description, and ALL four prior results.
  → This closes the incident.

═══ FINAL RESPONSE ══════════════════════════════════════════════════════

After the final tool call, respond with ONLY this JSON:
{
  "incident_number": "<number>",
  "outcome": "resolved" | "pending",
  "triage_action": "assigned" | "pending",
  "ci_valid": <bool>,
  "escalated_to_cat_a": <bool>,
  "order_cancelled": <bool>,
  "order_id": "<id or null>",
  "summary": "<one paragraph narrative of everything that happened>"
}

Rules:
- Never skip a step unless triage result is "pending".
- Never call run_resolution if triage action was "pending".
- Always pass full result objects (not just individual fields) to run_resolution.
- Pass order_value as 0 (not null) to run_priority_assessment if triage returned null.
"""


class SuperOrchestratorAgent:
    """
    Master coordinator. Treats sub-agents as tools via Claude's tool_use API.
    Runs its own agentic loop (does not extend BaseAgent due to custom dispatch).
    """

    def __init__(self, sn: ServiceNowClient, order_api: OrderAPIClient) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        # Sub-agents — instantiated once, stateless per run
        self._triage       = TriageAgent(sn)
        self._ci           = CIValidationAgent(sn)
        self._priority     = PriorityAgent(sn)
        self._cancellation = OrderCancellationAgent(sn, order_api)
        self._resolution   = ResolutionAgent(sn)

    def run(self, incident: Incident) -> dict:
        """Orchestrate the full lifecycle for one incident. Returns summary dict."""
        log.info("SuperOrchestrator starting for incident %s", incident.number)

        messages = [{"role": "user", "content": (
            f"Orchestrate the full lifecycle for this ServiceNow incident.\n\n"
            f"Incident Number : {incident.number}\n"
            f"sys_id          : {incident.sys_id}\n"
            f"Short Description: {incident.short_description}\n"
            f"Reported CI     : {incident.reported_ci or '(empty)'}\n"
            f"Current State   : {incident.state}\n\n"
            f"Full Description:\n{incident.description or '(no description provided)'}"
        )}]

        for iteration in range(MAX_ORCHESTRATOR_ITERATIONS):
            log.debug("SuperOrchestrator iteration %d", iteration + 1)

            response = self._client.messages.create(
                model="claude-opus-4-5",
                max_tokens=8192,
                system=_SYSTEM_PROMPT,
                tools=_TOOLS,
                messages=messages,
            )

            messages.append({"role": "assistant", "content": response.content})
            log.debug("SuperOrchestrator stop_reason=%s", response.stop_reason)

            if response.stop_reason == "end_turn":
                final_text = self._extract_text(response.content)
                log.info("SuperOrchestrator complete for %s", incident.number)
                return self._parse_json(final_text, "SuperOrchestrator")

            if response.stop_reason == "tool_use":
                tool_results = []
                for block in response.content:
                    if block.type != "tool_use":
                        continue
                    log.info("SuperOrchestrator → dispatching sub-agent: %s", block.name)
                    try:
                        result = self._dispatch(block.name, block.input, incident)
                        content = json.dumps(result)
                        is_error = False
                    except Exception as exc:
                        log.error("Sub-agent %s failed: %s", block.name, exc)
                        content = json.dumps({"error": str(exc), "agent": block.name})
                        is_error = True
                    log.debug("%s result: %s", block.name, content[:300])
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                        "is_error": is_error,
                    })
                messages.append({"role": "user", "content": tool_results})
            else:
                log.warning("SuperOrchestrator unexpected stop_reason=%s", response.stop_reason)
                break

        log.error("SuperOrchestrator max iterations reached for %s", incident.number)
        return {"outcome": "error", "incident_number": incident.number,
                "message": "Max orchestrator iterations reached."}

    # ── Sub-agent dispatch ─────────────────────────────────────────────────────

    def _dispatch(self, tool_name: str, tool_input: dict, incident: Incident) -> dict:
        """Route SuperOrchestrator tool calls to the correct sub-agent."""

        if tool_name == "run_triage":
            raw = self._triage.run_for_incident(Incident(
                sys_id=tool_input["sys_id"],
                number=tool_input["incident_number"],
                short_description=tool_input["short_description"],
                description=tool_input["description"],
                state=incident.state,
            ))
            return self._parse_json(raw, "TriageAgent")

        if tool_name == "run_ci_validation":
            raw = self._ci.run_for_incident(Incident(
                sys_id=tool_input["sys_id"],
                number=tool_input["incident_number"],
                short_description=incident.short_description,
                description=incident.description,
                state=incident.state,
                reported_ci=tool_input.get("reported_ci", ""),
            ))
            return self._parse_json(raw, "CIValidationAgent")

        if tool_name == "run_priority_assessment":
            raw = self._priority.run_for_incident(
                Incident(
                    sys_id=tool_input["sys_id"],
                    number=tool_input["incident_number"],
                    short_description=incident.short_description,
                    description=incident.description,
                    state=incident.state,
                ),
                triage_result={
                    "order_value": tool_input.get("order_value", 0),
                    "has_frustration": tool_input.get("has_frustration", False),
                },
            )
            return self._parse_json(raw, "PriorityAgent")

        if tool_name == "run_order_cancellation":
            raw = self._cancellation.run_for_incident(
                incident=Incident(
                    sys_id=tool_input["sys_id"],
                    number=tool_input["incident_number"],
                    short_description=incident.short_description,
                    description=incident.description,
                    state=incident.state,
                ),
                order_id=tool_input.get("order_id") or None,
            )
            return self._parse_json(raw, "OrderCancellationAgent")

        if tool_name == "run_resolution":
            raw = self._resolution.run_for_incident(
                incident=Incident(
                    sys_id=tool_input["sys_id"],
                    number=tool_input["incident_number"],
                    short_description=tool_input["short_description"],
                    description=incident.description,
                    state=incident.state,
                ),
                triage_result=tool_input.get("triage_result", {}),
                ci_result=tool_input.get("ci_result", {}),
                priority_result=tool_input.get("priority_result", {}),
                cancel_result=tool_input.get("cancel_result", {}),
            )
            return self._parse_json(raw, "ResolutionAgent")

        raise ValueError(f"SuperOrchestrator: unknown sub-agent tool '{tool_name}'")

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(raw: str, agent_name: str) -> dict:
        cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            log.warning("%s returned non-JSON: %s", agent_name, raw[:200])
            return {"raw_response": raw, "parse_error": True, "agent": agent_name}

    @staticmethod
    def _extract_text(blocks: list) -> str:
        return "\n".join(
            b.text for b in blocks if hasattr(b, "type") and b.type == "text"
        ).strip()
