# Incident Orchestrator — Multi-Agent Edition

An **agentic AI system** that fully automates the ServiceNow incident lifecycle using a hierarchy of Claude-powered specialist agents. Each stage of the workflow is handled by a dedicated agent with its own tools, context, and decision logic.

---

## Architecture

```
SuperOrchestratorAgent  (claude-opus-4-5)
        │
        ├─── run_triage           ──▶  TriageAgent           (claude-3-5-sonnet)
        ├─── run_ci_validation    ──▶  CIValidationAgent      (claude-3-5-haiku)
        ├─── run_priority_assessment ▶ PriorityAgent          (claude-3-5-haiku)
        ├─── run_order_cancellation ▶  OrderCancellationAgent (claude-3-5-haiku)
        └─── run_resolution       ──▶  ResolutionAgent        (claude-3-5-sonnet)
```

The **SuperOrchestratorAgent** treats every specialist as a Claude *tool*. It decides the execution sequence, passes context between agents, and enforces the 7-step lifecycle below.

---

## Incident Lifecycle (7 Steps)

| Step | Agent | Action |
|------|-------|--------|
| 1 | Poller | Polls ServiceNow every N seconds for new unassigned incidents |
| 2 | TriageAgent | Validates info quality — assigns incident or sets Pending with missing fields |
| 3 | CIValidationAgent | Verifies the Reported CI (cmdb_ci) field; adds work note if empty |
| 4 | PriorityAgent | Sets PCC = CAT A if order value > $5,000 **and** user frustration detected |
| 5 | OrderCancellationAgent | Calls the Order Management API to cancel the order |
| 6 | ResolutionAgent | Writes structured resolution notes (Issue / Error / Recovery steps) |
| 7 | ResolutionAgent | Resolves the incident (state=6, assigned_to=engineer) |

### Pending Path
If the TriageAgent determines the incident lacks sufficient information, it:
1. Moves the incident to **Pending** state
2. Adds a work note listing exactly what is missing
3. **Stops** — no further agents are invoked for that incident

---

## Project Structure

```
incident-orchestrator-agents/
├── agents/
│   ├── base_agent.py             # Agentic loop base class (all sub-agents inherit this)
│   ├── triage_agent.py           # Step 2: info quality + assign/pending
│   ├── ci_validation_agent.py    # Step 3: validates Reported CI field
│   ├── priority_agent.py         # Step 4: CAT A escalation
│   ├── order_cancellation_agent.py  # Step 5: cancel order via API
│   ├── resolution_agent.py       # Steps 6+7: notes + resolve
│   └── super_orchestrator.py     # Master coordinator — dispatches sub-agents as tools
│
├── tools/
│   ├── servicenow_tools.py       # Anthropic tool definitions + SN handler functions
│   └── order_tools.py            # Anthropic tool definition + order cancel handler
│
├── clients/
│   ├── servicenow.py             # ServiceNow Table API wrapper (CRUD)
│   ├── order_api.py              # Order cancellation REST API client (stub-safe)
│   └── llm.py                    # Direct Claude LLM client (API compat; TriageAgent preferred)
│
├── orchestrator/
│   └── pipeline.py               # Thin adapter: run(incident) → SuperOrchestratorAgent
│
├── poller/
│   └── scheduler.py              # APScheduler-based polling loop
│
├── config/
│   └── settings.py               # Pydantic BaseSettings — all config from .env
│
├── models/
│   └── incident.py               # Incident, LLMAssessment, CancelResult dataclasses
│
├── utils/
│   └── logger.py                 # Dual-handler logger (stdout INFO + file DEBUG)
│
├── main.py                       # Entry point
├── requirements.txt
└── .env.example                  # Environment variable template
```

---

## Setup

### 1. Clone & install

```bash
git clone https://github.com/sdas25989-ops/incident-orchestrator-agents.git
cd incident-orchestrator-agents

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your real values
```

| Variable | Description |
|----------|-------------|
| `SERVICENOW_INSTANCE` | Your SN instance URL, e.g. `https://myco.service-now.com` |
| `SN_USER` | ServiceNow agent account username |
| `SN_PASS` | ServiceNow agent account password |
| `SN_GROUP` | Exact name of the assignment group to monitor |
| `SN_PCC_FIELD` | API field name for Problem Correlation Code (right-click field → *Show Field Name*) |
| `ANTHROPIC_API_KEY` | Your Anthropic API key (`sk-ant-...`) |
| `ORDER_API_BASE_URL` | Internal Order Management API base URL (leave `localhost:9999` for stub mode) |
| `ORDER_API_KEY` | Bearer token for the Order Management API |
| `ENGINEER_NAME` | Name written to `assigned_to` on resolution |
| `POLL_INTERVAL_SECONDS` | How often to poll ServiceNow (default: 60) |

### 3. Run

```bash
python3 main.py
```

Logs are written to both stdout and `logs/orchestrator.log`.

---

## Agent Details

### BaseAgent (`agents/base_agent.py`)
Abstract base class providing the full Anthropic agentic loop:
- Sends messages to Claude with tool definitions
- On `stop_reason == "tool_use"`: executes every tool call, accumulates results, loops
- On `stop_reason == "end_turn"`: returns Claude's final text
- Guard: `MAX_ITERATIONS = 20` prevents runaway loops

### SuperOrchestratorAgent (`agents/super_orchestrator.py`)
- Model: `claude-opus-4-5`
- Treats the 5 specialist agents as Claude tools (`run_triage`, `run_ci_validation`, etc.)
- Enforces the mandatory execution sequence via system prompt
- Stops early if TriageAgent returns `action = "pending"`
- Returns a structured JSON summary of the full incident run

### TriageAgent (`agents/triage_agent.py`)
- Model: `claude-3-5-sonnet-20241022`
- Tools: `sn_assign_incident`, `sn_set_pending`
- Assesses info completeness, extracts order_id / order_value / frustration
- Returns: `{action, order_id, order_value, has_frustration, missing_fields, reasoning}`

### CIValidationAgent (`agents/ci_validation_agent.py`)
- Model: `claude-3-5-haiku-20241022`
- Tool: `sn_add_work_note`
- Checks whether `cmdb_ci` (Reported CI) is populated; adds a note if empty
- Non-blocking — pipeline always continues after this step

### PriorityAgent (`agents/priority_agent.py`)
- Model: `claude-3-5-haiku-20241022`
- Tools: `sn_set_pcc`, `sn_add_work_note`
- Sets PCC = `CAT A` only when `order_value > 5000` **AND** `has_frustration = true`
- Returns: `{escalated, pcc, reason}`

### OrderCancellationAgent (`agents/order_cancellation_agent.py`)
- Model: `claude-3-5-haiku-20241022`
- Tools: `cancel_order`, `sn_add_work_note`
- Calls the Order Management API; adds a work note with the outcome
- Returns: `{success, order_id, message}`

### ResolutionAgent (`agents/resolution_agent.py`)
- Model: `claude-3-5-sonnet-20241022`
- Tool: `sn_resolve_incident`
- Writes resolution notes using the **Issue / Error / Recovery steps** template
- Resolves the incident (state=6) and assigns it to the engineer
- Returns: `{resolved, close_notes}`

---

## Stub / Mock Mode

The Order Cancellation API runs in **stub mode** by default (when `ORDER_API_BASE_URL` is `http://localhost:9999` or `ORDER_API_KEY` is empty). In stub mode, no real HTTP calls are made — a simulated success response is returned so the full pipeline can be tested without a live Order API.

---

## Logs

- **Console**: INFO level and above
- **File** (`logs/orchestrator.log`): DEBUG level and above — every tool call, LLM iteration, and state transition is recorded

---

## Requirements

- Python 3.10+
- See `requirements.txt`:
  - `anthropic >= 0.28.0`
  - `requests >= 2.31.0`
  - `pydantic >= 2.0.0`
  - `pydantic-settings >= 2.0.0`
  - `apscheduler >= 3.10.0`
  - `python-dotenv >= 1.0.0`

---

## Notes

- The `SN_PCC_FIELD` variable must match the exact API field name in your ServiceNow instance. To find it: open any incident → right-click the PCC label → *Show Field Name*. Common values: `u_problem_correlation_code`, `u_pcc`.
- The `close_code` sent on resolution defaults to `"Solved (Permanently)"` — adjust in `clients/servicenow.py` to match your instance's picklist values if needed.
- All custom ServiceNow fields prefixed with `u_` are instance-specific.
