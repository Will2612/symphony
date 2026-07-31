# Handoff Report — Worker M2 (Workflow & Config Documentation)

## 1. Observation

- **Target File Created**: `/home/will/Projects/symphony/docs/02_workflow_and_config.md`
- **Source Code Inspected**:
  - `elixir/lib/symphony_elixir/workflow.ex` (Lines 1-124): File path resolution, `split_front_matter/1`, `YamlElixir.read_from_string/1`, return format `{:ok, %{config: map, prompt: prompt, prompt_template: prompt}}`.
  - `elixir/lib/symphony_elixir/workflow_store.ex` (Lines 1-154): GenServer polling loop at 1,000ms interval (`@poll_interval_ms`), stamp tuple `{mtime, size, phash2(content)}`, error logging `log_reload_error/2`, retaining last known good state.
  - `elixir/lib/symphony_elixir/config/schema.ex` (Lines 1-558): Ecto embedded schema root embedding `Tracker`, `Polling`, `Workspace`, `Worker`, `Agent`, `Codex`, `Hooks`, `Observability`, `Server`. Implements `StringOrMap` custom Ecto type, `normalize_keys/1`, `drop_nil_values/1`, and `resolve_runtime_turn_sandbox_policy/3`.
  - `elixir/lib/symphony_elixir/config.ex` (Lines 1-155): Runtime accessors `settings/0`, `settings!/0`, `max_concurrent_agents_for_state/1`, `workflow_prompt/0`, `codex_turn_sandbox_policy/1`.
  - `elixir/lib/symphony_elixir/prompt_builder.ex` (Lines 1-65): `Solid.parse!/1` & `Solid.render!/3` integration, ISO-8601 struct serialization for dates/datetimes.
  - `elixir/WORKFLOW.md` (Lines 1-328): Front-matter YAML and Liquid prompt body reference file.

## 2. Logic Chain

1. **Requirement Mapping**: DISPATCH.md required detailed documentation covering `WORKFLOW.md` spec, `SymphonyElixir.Workflow` parsing mechanics, `SymphonyElixir.WorkflowStore` hot reloading, `SymphonyElixir.Config.Schema` Ecto sub-schemas, environment variable indirection, Liquid templating via `PromptBuilder`, and valid Mermaid diagrams.
2. **Analysis & Verification**: Examined the Elixir reference implementation files directly to ensure exact type signatures, default values, struct conversions, and error handling mechanics matched the actual codebase.
3. **Diagram Embedding**: Formulated two valid Mermaid diagrams (`flowchart TD` for parsing and caching pipeline, and `classDiagram` for the 9 embedded Ecto sub-schemas) to visually map out structural dependencies.
4. **Documentation Creation**: Authored `/home/will/Projects/symphony/docs/02_workflow_and_config.md` containing 8 comprehensive sections fully detailing policy vs mechanism, schema validation, and runtime indirection.

## 3. Caveats

No caveats. All sub-modules, type specs, fallback mechanics, and diagram structures were verified directly against the Elixir reference source code.

## 4. Conclusion

Worker M2 has completed the creation of `/home/will/Projects/symphony/docs/02_workflow_and_config.md`. The documentation accurately and comprehensively reflects the workflow and configuration architecture of Symphony, including valid Mermaid diagrams and complete technical specifications.

## 5. Verification Method

- **File Inspection**:
  - Read `/home/will/Projects/symphony/docs/02_workflow_and_config.md` and confirm all 8 sections are present.
  - Verify Mermaid diagrams syntax in a Mermaid renderer or live parser.
- **Code Fidelity Verification**:
  - Compare schema field definitions in section 2.1 & 5 with `elixir/lib/symphony_elixir/config/schema.ex`.
  - Compare `WorkflowStore` stamp tuple and polling interval with `elixir/lib/symphony_elixir/workflow_store.ex`.
