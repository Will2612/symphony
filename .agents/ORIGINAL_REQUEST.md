# Original User Request

## 2026-07-31T13:55:38Z

# Teamwork Project Prompt — Draft

> Status: Ready for launch — awaiting user approval
> Goal: Craft prompt → get user approval → delegate to teamwork_preview

Investigate the previously undocumented utility and mix task modules in the codebase and generate a dedicated Markdown document for them to complete our 100% coverage goal.

Working directory: /home/will/Projects/symphony
Integrity mode: development

## Requirements

### R1. Target Modules Analysis
Analyze the following specific files that were previously uncovered or only briefly mentioned:
- `elixir/lib/symphony_elixir_web/error_html.ex`
- `elixir/lib/symphony_elixir_web/error_json.ex`
- `elixir/lib/symphony_elixir/log_file.ex`
- `elixir/lib/mix/tasks/pr_body.check.ex`
- `elixir/lib/mix/tasks/specs.check.ex`

### R2. Documentation Generation
Generate a detailed Markdown document named `08_utilities_and_mix_tasks.md` in the `docs/` directory. It should provide a deep dive into the functionality, logic, and structure of these 5 modules.

### R3. Diagram Creation
Embed at least one Mermaid diagram within the Markdown documentation to illustrate the workflow, data flow, or architectural dependencies of these utilities (e.g., a flowchart for the custom Mix tasks).

## Acceptance Criteria

### Verification
- [ ] A new file `docs/08_utilities_and_mix_tasks.md` is created.
- [ ] The document explicitly details all 5 target modules.
- [ ] The document contains at least one Mermaid diagram block.
- [ ] The Mermaid diagram possesses valid syntax and can be rendered without errors.
- [ ] The documentation accurately reflects the current state of these modules in the codebase.
