"""
ServiceNow incident poller.

Uses APScheduler to run a periodic job that:
1. Queries ServiceNow for new/open, unassigned incidents in the configured group
2. Submits each incident to the IncidentPipeline for processing

The scheduler runs the pipeline synchronously in the same thread to keep
things simple and avoid race conditions on the processed-IDs set.
"""

import signal
import time

from apscheduler.schedulers.background import BackgroundScheduler

from clients.llm import LLMClient
from clients.order_api import OrderAPIClient
from clients.servicenow import ServiceNowClient
from config.settings import settings
from orchestrator.pipeline import IncidentPipeline
from utils.logger import get_logger

log = get_logger(__name__)


class IncidentPoller:
    def __init__(
        self,
        sn: ServiceNowClient,
        pipeline: IncidentPipeline,
    ) -> None:
        self._sn = sn
        self._pipeline = pipeline
        self._scheduler = BackgroundScheduler()

    def start(self) -> None:
        """Start the polling scheduler and block until interrupted."""
        interval = settings.poll_interval_seconds
        log.info(
            "Starting incident poller — group='%s'  interval=%ds",
            settings.sn_group,
            interval,
        )

        self._scheduler.add_job(
            self._poll_and_process,
            trigger="interval",
            seconds=interval,
            id="incident_poller",
            max_instances=1,          # prevent overlap if a run takes too long
            coalesce=True,
        )
        self._scheduler.start()

        # Run once immediately on startup
        self._poll_and_process()

        # Block main thread; shut down cleanly on SIGINT / SIGTERM
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        log.info("Poller running. Press Ctrl+C to stop.")
        try:
            while True:
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            self._shutdown()

    def _poll_and_process(self) -> None:
        """Fetch open incidents and run each through the pipeline."""
        log.info("--- Poll cycle start ---")
        try:
            incidents = self._sn.get_new_incidents(settings.sn_group)
        except Exception as exc:
            log.error("Failed to poll ServiceNow: %s", exc)
            return

        if not incidents:
            log.info("No new incidents found.")
            return

        for incident in incidents:
            try:
                self._pipeline.run(incident)
            except Exception as exc:
                log.exception(
                    "Unhandled error processing incident %s: %s",
                    incident.number, exc,
                )

        log.info("--- Poll cycle end — processed %d incident(s) ---", len(incidents))

    def _handle_shutdown(self, signum, frame) -> None:
        self._shutdown()

    def _shutdown(self) -> None:
        log.info("Shutting down scheduler...")
        self._scheduler.shutdown(wait=False)
        raise SystemExit(0)
