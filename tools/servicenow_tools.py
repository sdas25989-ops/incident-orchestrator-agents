"""
ServiceNow tool definitions (Anthropic format) and their handler functions.

Each tool definition is a dict that Claude sees when deciding what action to take.
Each handler is a plain Python function that calls the ServiceNowClient.
"""

from clients.servicenow import ServiceNowClient
from config.settings import settings

# ── Tool Definitions ───────────────────────────────────────────────────────────

TOOL_SN_ASSIGN_INCIDENT = {
    "name": "sn_assign_incident",
    "description": (
        "Assign a ServiceNow incident to the orchestrator engineer and set its "
        "state to In-Progress. Call this as the first action when picking up an incident."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sys_id": {
                "type": "string",
                "description": "The ServiceNow sys_id of the incident to assign."
            }
        },
        "required": ["sys_id"]
    }
}

TOOL_SN_SET_PENDING = {
    "name": "sn_set_pending",
    "description": (
        "Move a ServiceNow incident to Pending state when there is insufficient "
        "information to process it. Adds a work note listing exactly what is missing."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sys_id": {
                "type": "string",
                "description": "The ServiceNow sys_id of the incident."
            },
            "missing_fields": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of fields or details that are missing from the incident."
            }
        },
        "required": ["sys_id", "missing_fields"]
    }
}

TOOL_SN_ADD_WORK_NOTE = {
    "name": "sn_add_work_note",
    "description": "Append an internal work note (visible only to agents) to a ServiceNow incident.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sys_id": {
                "type": "string",
                "description": "The ServiceNow sys_id of the incident."
            },
            "note": {
                "type": "string",
                "description": "The work note text to append."
            }
        },
        "required": ["sys_id", "note"]
    }
}

TOOL_SN_SET_PCC = {
    "name": "sn_set_pcc",
    "description": (
        "Set the Problem Correlation Code (PCC) field on a ServiceNow incident. "
        "Use 'CAT A' when order_value > $5000 AND user frustration are both detected."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sys_id": {
                "type": "string",
                "description": "The ServiceNow sys_id of the incident."
            },
            "category": {
                "type": "string",
                "enum": ["CAT A", "CAT B", "CAT C"],
                "description": "The PCC category to set. 'CAT A' is highest priority."
            }
        },
        "required": ["sys_id", "category"]
    }
}

TOOL_SN_RESOLVE_INCIDENT = {
    "name": "sn_resolve_incident",
    "description": (
        "Resolve a ServiceNow incident: state=Resolved, engineer assigned, close notes written. "
        "This is always the FINAL action. Do not call after this."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sys_id": {
                "type": "string",
                "description": "The ServiceNow sys_id of the incident."
            },
            "close_notes": {
                "type": "string",
                "description": (
                    "Structured resolution notes using the template:\n"
                    "Issue: <what the user reported>\n"
                    "Error: <specific error or problem identified>\n"
                    "Recovery steps: <what was done to resolve it>"
                )
            }
        },
        "required": ["sys_id", "close_notes"]
    }
}

# ── Handler Functions ──────────────────────────────────────────────────────────

def handle_sn_assign_incident(sn: ServiceNowClient, tool_input: dict) -> dict:
    sn.assign_to_engineer(tool_input["sys_id"], settings.engineer_name)
    return {
        "status": "success",
        "message": f"Incident assigned to {settings.engineer_name}, state → In-Progress."
    }


def handle_sn_set_pending(sn: ServiceNowClient, tool_input: dict) -> dict:
    sys_id = tool_input["sys_id"]
    missing = tool_input["missing_fields"]
    reason = (
        "The incident does not contain enough information to begin investigation.\n"
        "Please provide the following details:\n" +
        "\n".join(f"  - {f}" for f in missing)
    )
    sn.set_pending(sys_id, reason)
    return {"status": "success", "message": f"Incident set to Pending. Missing: {missing}"}


def handle_sn_add_work_note(sn: ServiceNowClient, tool_input: dict) -> dict:
    sn.add_work_note(tool_input["sys_id"], tool_input["note"])
    return {"status": "success", "message": "Work note added."}


def handle_sn_set_pcc(sn: ServiceNowClient, tool_input: dict) -> dict:
    sys_id = tool_input["sys_id"]
    category = tool_input["category"]
    sn.set_pcc(sys_id, category)
    sn.add_work_note(
        sys_id,
        f"[PriorityAgent] Problem Correlation Code escalated to {category}."
    )
    return {"status": "success", "message": f"PCC set to {category}."}


def handle_sn_resolve_incident(sn: ServiceNowClient, tool_input: dict) -> dict:
    sn.resolve_incident(tool_input["sys_id"], tool_input["close_notes"], settings.engineer_name)
    return {"status": "success", "message": "Incident resolved."}


# ── Dispatch tables ────────────────────────────────────────────────────────────

SN_TOOL_DEFINITIONS = [
    TOOL_SN_ASSIGN_INCIDENT,
    TOOL_SN_SET_PENDING,
    TOOL_SN_ADD_WORK_NOTE,
    TOOL_SN_SET_PCC,
    TOOL_SN_RESOLVE_INCIDENT,
]

SN_TOOL_HANDLERS = {
    "sn_assign_incident":  handle_sn_assign_incident,
    "sn_set_pending":      handle_sn_set_pending,
    "sn_add_work_note":    handle_sn_add_work_note,
    "sn_set_pcc":          handle_sn_set_pcc,
    "sn_resolve_incident": handle_sn_resolve_incident,
}
