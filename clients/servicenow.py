"""
ServiceNow Table API client.

Wraps all CRUD operations needed by the incident orchestrator.
Authenticates with basic auth (SN_USER / SN_PASS).
"""

import requests
from requests.auth import HTTPBasicAuth
from typing import Optional

from config.settings import settings
from models.incident import Incident
from utils.logger import get_logger

log = get_logger(__name__)

# ServiceNow incident state codes
STATE_NEW = "1"
STATE_IN_PROGRESS = "2"
STATE_PENDING = "4"
STATE_RESOLVED = "6"

# Base fields fetched from SN on every poll.
# The Problem Correlation Code (PCC) field is appended dynamically via
# settings.sn_pcc_field because its API name differs between instances.
_BASE_FIELDS = [
    "sys_id",
    "number",
    "short_description",
    "description",
    "state",
    "caller_id",
    "assigned_to",
    "assignment_group",
    "cmdb_ci",          # Reported CI
    "work_notes",
    "close_notes",
]


class ServiceNowClient:
    def __init__(self) -> None:
        self._base = settings.servicenow_instance.rstrip("/")
        self._auth = HTTPBasicAuth(settings.sn_user, settings.sn_pass)
        self._headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def _fields(self) -> str:
        """Return the comma-separated field list including the PCC field."""
        return ",".join(_BASE_FIELDS + [settings.sn_pcc_field])

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get_new_incidents(self, group: str) -> list[Incident]:
        """
        Return all incidents in the given assignment group that are in
        New (1) or In-Progress (2) state and not yet assigned to anyone.
        """
        params = {
            "sysparm_query": (
                f"assignment_group.name={group}"
                f"^stateIN{STATE_NEW},{STATE_IN_PROGRESS}"
                f"^assigned_to=NULL"
            ),
            "sysparm_fields": self._fields(),
            "sysparm_limit": "50",
            "sysparm_display_value": "true",
        }
        resp = requests.get(
            self._url("/api/now/table/incident"),
            params=params,
            auth=self._auth,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
        records = resp.json().get("result", [])
        log.info("Polled ServiceNow — found %d open incident(s) in group '%s'", len(records), group)
        return [self._to_incident(r) for r in records]

    def get_incident(self, sys_id: str) -> Optional[Incident]:
        """Fetch a single incident by sys_id."""
        params = {
            "sysparm_fields": self._fields(),
            "sysparm_display_value": "true",
        }
        resp = requests.get(
            self._url(f"/api/now/table/incident/{sys_id}"),
            params=params,
            auth=self._auth,
            headers=self._headers,
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return self._to_incident(resp.json()["result"])

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def update_incident(self, sys_id: str, payload: dict) -> None:
        """Generic PATCH — pass any SN field/value pairs."""
        resp = requests.patch(
            self._url(f"/api/now/table/incident/{sys_id}"),
            json=payload,
            auth=self._auth,
            headers=self._headers,
            timeout=30,
        )
        resp.raise_for_status()
        log.debug("Updated incident %s with %s", sys_id, list(payload.keys()))

    def assign_to_engineer(self, sys_id: str, engineer_name: str) -> None:
        """Set state to In-Progress and assigned_to the engineer."""
        self.update_incident(sys_id, {
            "state": STATE_IN_PROGRESS,
            "assigned_to": engineer_name,
        })
        log.info("Assigned incident %s to '%s'", sys_id, engineer_name)

    def add_work_note(self, sys_id: str, note: str) -> None:
        """Append a work note (internal note visible only to agents)."""
        self.update_incident(sys_id, {"work_notes": note})
        log.debug("Work note added to %s", sys_id)

    def set_pending(self, sys_id: str, reason: str) -> None:
        """
        Move incident to Pending state and add a work note explaining
        what information is needed from the user.
        """
        self.update_incident(sys_id, {
            "state": STATE_PENDING,
            "work_notes": (
                f"[Orchestrator] Incident moved to Pending — additional information required.\n"
                f"{reason}"
            ),
        })
        log.info("Incident %s moved to PENDING. Reason: %s", sys_id, reason)

    def set_pcc(self, sys_id: str, category: str) -> None:
        """Update the Problem Correlation Code (PCC) field on the incident."""
        self.update_incident(sys_id, {settings.sn_pcc_field: category})
        log.info("Incident %s PCC (%s) set to '%s'", sys_id, settings.sn_pcc_field, category)

    def resolve_incident(
        self,
        sys_id: str,
        close_notes: str,
        engineer_name: str,
    ) -> None:
        """
        Resolve the incident:
        - state = Resolved (6)
        - assigned_to = engineer
        - close_notes = resolution notes
        - close_code = "Solved (Permanently)" — adjust to match your SN instance
        """
        self.update_incident(sys_id, {
            "state": STATE_RESOLVED,
            "assigned_to": engineer_name,
            "close_notes": close_notes,
            "close_code": "Solved (Permanently)",
        })
        log.info("Incident %s RESOLVED and assigned to '%s'", sys_id, engineer_name)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _field_value(record: dict, key: str) -> str:
        """
        ServiceNow returns fields as either a plain string or a dict with
        {"display_value": ..., "value": ..., "link": ...} when display_value=true.
        This helper normalises both formats.
        """
        raw = record.get(key, "")
        if isinstance(raw, dict):
            return raw.get("display_value") or raw.get("value") or ""
        return raw or ""

    @staticmethod
    def _field_link(record: dict, key: str) -> str:
        raw = record.get(key, "")
        if isinstance(raw, dict):
            return raw.get("link") or ""
        return ""

    def _to_incident(self, r: dict) -> Incident:
        return Incident(
            sys_id=r.get("sys_id", ""),
            number=self._field_value(r, "number"),
            short_description=self._field_value(r, "short_description"),
            description=self._field_value(r, "description"),
            state=self._field_value(r, "state"),
            caller_id=self._field_value(r, "caller_id"),
            assigned_to=self._field_value(r, "assigned_to"),
            assignment_group=self._field_value(r, "assignment_group"),
            reported_ci=self._field_value(r, "cmdb_ci"),
            reported_ci_link=self._field_link(r, "cmdb_ci"),
            pcc=self._field_value(r, settings.sn_pcc_field),
            work_notes=self._field_value(r, "work_notes"),
            close_notes=self._field_value(r, "close_notes"),
        )
