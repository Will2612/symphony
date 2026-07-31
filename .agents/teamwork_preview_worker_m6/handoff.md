# Handoff Report — Worker M6 (Agent Execution & Codex Protocol Doc)

## 1. Observation
- Source modules inspected:
  - `elixir/lib/symphony_elixir/agent_runner.ex`: Lines 1–204. `AgentRunner.run/3`, `run_on_worker_host/4`, `run_codex_turns/5`, `do_run_codex_turns/8`, `continue_with_issue?/2`, `build_turn_prompt/4`, `selected_worker_host/2`.
  - `elixir/lib/symphony_elixir/prompt_builder.ex`: Lines 1–65. `PromptBuilder.build_prompt/2`, `@render_opts` (`strict_variables: true`, `strict_filters: true`), `to_solid_map/1`, `to_solid_value/1` (ISO8601 formatting for DateTime, NaiveDateTime, Date, Time), `default_prompt/1`.
  - `elixir/lib/symphony_elixir/codex/app_server.ex`: Lines 1–1099. `AppServer.start_session/2`, `run_turn/4`, `send_initialize/1`, `start_thread/3`, `start_turn/7`, `await_turn_completion/4`, `receive_loop/6`, `handle_incoming/6`, `maybe_handle_approval_request/8`, `approve_or_require/8`, `maybe_auto_answer_tool_request_user_input/8`.
  - `elixir/lib/symphony_elixir/codex/dynamic_tool.ex`: Lines 1–210. `DynamicTool.execute/3`, `tool_specs/0`, `@linear_graphql_input_schema`, `normalize_linear_graphql_arguments/1`, `graphql_response/1`, `dynamic_tool_response/2`.
- Documentation file created:
  - Path: `/home/will/Projects/symphony/docs/06_agent_execution_and_codex.md` (Total 7 core sections, embedded Mermaid sequence diagram, state diagram flow, data tables, and Elixir/JSON-RPC 2.0 code snippets).

## 2. Logic Chain
- Step 1: Investigated `AgentRunner.ex` to extract worker task supervision (`Task.Supervisor`), workspace initialization (`Workspace.create_for_issue`), pre/post run hook execution (`try ... after`), multi-turn loop control (`run_codex_turns`), `max_turns` limit enforcement, and Linear issue state refresh (`continue_with_issue?/2`).
- Step 2: Investigated `PromptBuilder.ex` to trace Liquid workflow template resolution from `Workflow.current()`, `Solid.parse!/1`, `Solid.render!/3` strict variable/filter enforcement, struct-to-map conversion (`to_solid_map`), and ISO8601 string formatting for temporal types.
- Step 3: Investigated `Codex.AppServer` to document stdio/SSH Erlang Port streaming (`Port.open`, `SSH.start_port`), JSON-RPC 2.0 protocol handshake (`initialize`, `initialized`, `thread/start`, `turn/start`), notification & event stream parsing (`receive_loop/6`), auto-approval policies (`approval_policy` "never" -> `auto_approve_requests: true`), and non-interactive input auto-answering (`@non_interactive_tool_input_answer`).
- Step 4: Investigated `Codex.DynamicTool` to detail dynamic client tool specs (`linear_graphql`), argument normalization (string or object format), delegation to `Linear.Client.graphql/3`, and response payload structure (`success`, `output`, `contentItems`).
- Step 5: Synthesized all findings into `/home/will/Projects/symphony/docs/06_agent_execution_and_codex.md` with a complete Mermaid `sequenceDiagram` depicting the full flow across all components.

## 3. Caveats
- No caveats. The documentation directly reflects the exact module logic, type specifications, and function calls present in the Elixir codebase.

## 4. Conclusion
- Comprehensive documentation for Agent Execution and the Codex App-Server JSON-RPC 2.0 Protocol has been successfully written to `/home/will/Projects/symphony/docs/06_agent_execution_and_codex.md`.
- All requirements specified in `DISPATCH.md` have been met, including `AgentRunner` lifecycle, `PromptBuilder` Solid templates, Codex JSON-RPC protocol, `DynamicTool` execution, and a valid Mermaid sequence diagram.

## 5. Verification Method
- Inspect document path: `/home/will/Projects/symphony/docs/06_agent_execution_and_codex.md`.
- Validate Mermaid diagram syntax using any standard Mermaid parser or renderer.
- Compare documented function names (`run_codex_turns/5`, `build_prompt/2`, `start_session/2`, `execute/3`), structs, and JSON-RPC method names (`initialize`, `thread/start`, `turn/start`, `item/tool/call`) against `elixir/lib/symphony_elixir/agent_runner.ex`, `prompt_builder.ex`, `codex/app_server.ex`, and `codex/dynamic_tool.ex`.
