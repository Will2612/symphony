# Project Symphony Documentation Master Plan

## Architecture Overview
Symphony is an OTP-structured Elixir daemon application designed for autonomous coding agent orchestration. It manages workflow configurations, polls issue trackers (Linear), creates isolated workspaces, executes multi-turn Codex sessions via JSON-RPC 2.0 protocol over stdio/SSH, and provides real-time observability across ANSI terminal dashboards and Phoenix LiveView/REST APIs.

The 6 core business domains + overall system overview are fully documented in `docs/`:
1. `docs/01_architecture_overview.md`: System Architecture & OTP Supervision Hierarchy
2. `docs/02_workflow_and_config.md`: Workflow Policy & Ecto Configuration Schema
3. `docs/03_issue_tracker_integration.md`: Issue Tracker Abstraction & Linear GraphQL Adapter
4. `docs/04_orchestration_engine.md`: Orchestrator Engine, Polling Loop & State Machine
5. `docs/05_workspace_management.md`: Workspace Isolation, Path Safety & Lifecycle Hooks
6. `docs/06_agent_execution_and_codex.md`: Agent Execution, Codex Protocol & Dynamic Tools
7. `docs/07_observability_and_ui.md`: Observability Surface, Terminal UI & Phoenix Web/REST API

## Feature Inventory
| # | Feature / Domain | Description | Target Document | Milestone |
|---|------------------|-------------|-----------------|-----------|
| 1 | Overall System Architecture | OTP supervision tree, repository layout, entry points, SPEC.md alignment | `docs/01_architecture_overview.md` | M1 |
| 2 | Workflow & Config Schema | `WORKFLOW.md` YAML/Liquid parsing, `Config.Schema` Ecto validation, env vars | `docs/02_workflow_and_config.md` | M2 |
| 3 | Issue Tracker Integration | `Tracker` behaviour, `Linear.Adapter` GraphQL client, `Tracker.Memory` mock | `docs/03_issue_tracker_integration.md` | M3 |
| 4 | Core Orchestration Engine | `Orchestrator` GenServer loop, concurrency limits, state machine, retries | `docs/04_orchestration_engine.md` | M4 |
| 5 | Workspace Management | `Workspace` per-issue directory setup, `PathSafety`, hooks, SSH execution | `docs/05_workspace_management.md` | M5 |
| 6 | Agent Execution & Codex Protocol | `AgentRunner`, `PromptBuilder`, `Codex.AppServer` JSON-RPC stdio, `DynamicTool` | `docs/06_agent_execution_and_codex.md` | M6 |
| 7 | Observability & Web Dashboard | `StatusDashboard` ANSI TUI, `DashboardLive`, `ObservabilityPubSub`, REST API | `docs/07_observability_and_ui.md` | M7 |

## Milestones
| # | Name | Scope / Target File | Dependencies | Status |
|---|------|---------------------|-------------|--------|
| M1 | Architecture Overview Doc | `docs/01_architecture_overview.md` | Survey | DONE |
| M2 | Workflow & Config Doc | `docs/02_workflow_and_config.md` | M1 | DONE |
| M3 | Issue Tracker Integration Doc | `docs/03_issue_tracker_integration.md` | M1 | DONE |
| M4 | Core Orchestration Engine Doc | `docs/04_orchestration_engine.md` | M2, M3 | DONE |
| M5 | Workspace Management Doc | `docs/05_workspace_management.md` | M4 | DONE |
| M6 | Agent Execution & Codex Doc | `docs/06_agent_execution_and_codex.md` | M4, M5 | DONE |
| M7 | Observability & Web UI Doc | `docs/07_observability_and_ui.md` | M4, M6 | DONE |

## Code Layout & Output Boundaries
All generated documentation has been written to `docs/` in the project root:
- `/home/will/Projects/symphony/docs/01_architecture_overview.md`
- `/home/will/Projects/symphony/docs/02_workflow_and_config.md`
- `/home/will/Projects/symphony/docs/03_issue_tracker_integration.md`
- `/home/will/Projects/symphony/docs/04_orchestration_engine.md`
- `/home/will/Projects/symphony/docs/05_workspace_management.md`
- `/home/will/Projects/symphony/docs/06_agent_execution_and_codex.md`
- `/home/will/Projects/symphony/docs/07_observability_and_ui.md`

## Mermaid Diagram Requirements (Verification Checklist)
Every document contains at least one valid Mermaid diagram block (18 diagrams total across the suite):
- M1: System Supervision Tree & Startup Flow (`flowchart TD`, `graph TD`, `stateDiagram-v2`) — VERIFIED
- M2: Workflow & Config Schema Structure (`flowchart TD`, `classDiagram`) — VERIFIED
- M3: Tracker Behaviour & Linear Query Sequence Diagram (`classDiagram`, `sequenceDiagram`, `flowchart TD`) — VERIFIED
- M4: Orchestrator State Machine & Polling Loop (`flowchart TD`, `sequenceDiagram`, `stateDiagram-v2`) — VERIFIED
- M5: Workspace Hooks & Remote SSH Sequence (`sequenceDiagram`, `flowchart TD`) — VERIFIED
- M6: Codex Turn Loop & Dynamic Tool Protocol Sequence (`sequenceDiagram`) — VERIFIED
- M7: Observability Data Flow & LiveView PubSub Sequence (`flowchart TD`, `sequenceDiagram`) — VERIFIED
