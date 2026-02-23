"""
Incident Orchestration Pipeline — Multi-Agent Edition.

Thin adapter that delegates every incident to SuperOrchestratorAgent.
The poller and main.py interfaces are identical to the original system.
"""

from agents.super_orchestrator import SuperOrchestratorAgent
from clients.order_api import OrderAPIClient
from clients.servicenow import ServiceNowClient
from models.incident import Incident
from utils.logger import get_logger

log = get_logger(__name__)


class IncidentPipeline:
    def __init__(
        self,
        sn: ServiceNowClient,
        llm,                    # Accepted for API compatibility; unused in agent edition
        order_api: OrderAPIClient,
    ) -> None:
        self._orchestrator = SuperOrchestratorAgent(sn=sn, order_api=order_api)
        self._processed: set[str] = set()

    def run(self, incident: Incident) -> None:
        if incident.sys_id in self._processed:
            log.debug("[%s] Already processed this session — skipping", incident.number)
            return

        log.info("=" * 60)
        log.info("[Pipeline] Dispatching %s → SuperOrchestratorAgent", incident.number)
        log.info("=" * 60)

        try:
            result = self._orchestrator.run(incident)
            log.info(
                "[Pipeline] %s complete — outcome=%s order_cancelled=%s escalated=%s",
                incident.number,
                result.get("outcome"),
                result.get("order_cancelled"),
                result.get("escalated_to_cat_a"),
            )
        except Exception as exc:
            log.exception("[Pipeline] Unhandled error for %s: %s", incident.number, exc)
            return

        self._processed.add(incident.sys_id)
