"""
Incident Orchestrator — Multi-Agent Edition
Entry point. Reads .env, wires all clients, starts the polling loop.

Usage:
    python main.py
"""

from utils.logger import get_logger

log = get_logger("main")


def main() -> None:
    log.info("Initialising Incident Orchestrator (Multi-Agent Edition)...")

    try:
        from config.settings import settings
    except Exception as exc:
        log.error("Configuration error: %s", exc)
        log.error("Copy .env.example to .env and fill in all required values.")
        raise SystemExit(1)

    log.info(
        "Config loaded — instance=%s  group=%s  engineer='%s'",
        settings.servicenow_instance, settings.sn_group, settings.engineer_name,
    )

    from clients.servicenow import ServiceNowClient
    from clients.llm import LLMClient          # imported for API compat; not used by agents
    from clients.order_api import OrderAPIClient
    from orchestrator.pipeline import IncidentPipeline
    from poller.scheduler import IncidentPoller

    sn        = ServiceNowClient()
    llm       = LLMClient()
    order_api = OrderAPIClient()
    pipeline  = IncidentPipeline(sn=sn, llm=llm, order_api=order_api)
    poller    = IncidentPoller(sn=sn, pipeline=pipeline)

    poller.start()


if __name__ == "__main__":
    main()
