# Handoff Report — Structural Blueprint & Implementation Plan for `docs/08_utilities_and_mix_tasks.md`

**Agent ID**: `teamwork_preview_explorer_m1_1`  
**Working Directory**: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_m1_1`  
**Date/Timestamp**: `2026-07-31T14:05:00Z`  
**Target Output**: Structural Blueprint and Implementation Plan for `docs/08_utilities_and_mix_tasks.md`

---

## 1. Observation

### 1.1 Direct File Observations & Code Verification

A comprehensive audit of the 5 primary target modules and 2 helper modules was conducted directly on source files in `elixir/lib/`. The exact locations, line numbers, function signatures, and behavioral properties were verified as follows:

1. **`SymphonyElixirWeb.ErrorHTML`**
   - **Path**: `elixir/lib/symphony_elixir_web/error_html.ex` (9 lines total)
   - **Line 2**: `@moduledoc false`
   - **Line 4**: `@spec render(String.t(), map()) :: String.t()`
   - **Lines 5–7**: `def render(template, _assigns) do Phoenix.Controller.status_message_from_template(template) end`
   - **Behavior**: Phoenix HTML view for error rendering. Delegates template string resolution (e.g., `"404.html"`) to `Phoenix.Controller.status_message_from_template/1`, returning standard human-readable HTTP status text (e.g. `"Not Found"`).

2. **`SymphonyElixirWeb.ErrorJSON`**
   - **Path**: `elixir/lib/symphony_elixir_web/error_json.ex` (9 lines total)
   - **Line 2**: `@moduledoc false`
   - **Line 4**: `@spec render(String.t(), map()) :: map()`
   - **Lines 5–7**: `def render(template, _assigns) do %{error: %{code: "request_failed", message: Phoenix.Controller.status_message_from_template(template)}} end`
   - **Behavior**: Phoenix JSON view for REST API error rendering under `/api/v1/*`. Formats response as a standard error wrapper map with error code `"request_failed"`.

3. **`SymphonyElixir.LogFile`**
   - **Path**: `elixir/lib/symphony_elixir/log_file.ex` (81 lines total)
   - **Line 8**: `@handler_id :symphony_disk_log`
   - **Line 9**: `@default_log_relative_path "log/symphony.log"`
   - **Line 10**: `@default_max_bytes 10 * 1024 * 1024` (10 MB = 10,485,760 bytes)
   - **Line 11**: `@default_max_files 5`
   - **Lines 13–21**: `default_log_file/0` and `default_log_file/1` for path resolution using `Path.join/2` and `File.cwd!/0`.
   - **Lines 23–30**: `@spec configure() :: :ok` reads `:symphony_elixir, :log_file`, `:log_file_max_bytes`, and `:log_file_max_files`.
   - **Lines 32–50**: `setup_disk_handler/3` creates target directory via `File.mkdir_p/1`, removes existing `:symphony_disk_log` handler, adds `:logger_disk_log_h` handler with single-line formatting and `:wrap` type, and on success invokes `remove_default_console_handler/0`.
   - **Lines 60–66**: `remove_default_console_handler/0` removes `:logger.remove_handler(:default)` to prevent stdout log pollution over the ANSI `StatusDashboard` terminal UI.

4. **`Mix.Tasks.PrBody.Check`**
   - **Path**: `elixir/lib/mix/tasks/pr_body.check.ex` (217 lines total)
   - **Line 2**: `use Mix.Task`
   - **Lines 15–18**: `@template_paths [".github/pull_request_template.md", "../.github/pull_request_template.md"]`
   - **Lines 21–43**: `run/1` handles switches `--file <path>` (string) and `--help` / `-h` (boolean). Calls `read_template()`, `read_file/1`, `extract_template_headings/2`, and `lint_and_print/4`.
   - **Lines 77–87**: `extract_template_headings/2` scans template with `Regex.scan(~r/^\#{4,6}\s+.+$/m, template)`.
   - **Lines 101–107**: `lint/3` pipelines 4 validations: `check_required_headings`, `check_order`, `check_no_placeholders`, `check_sections_from_template`.
   - **Lines 131–169**: `check_sections_from_template/4` verifies section content is non-empty, checks for bullet item (`- `) requirements, and checkbox item (`- [ ] ` or `- [x] `) requirements based on template format.

5. **`Mix.Tasks.Specs.Check` & `SymphonyElixir.SpecsCheck`**
   - **Task Path**: `elixir/lib/mix/tasks/specs.check.ex` (54 lines total)
     - **Lines 11–12**: `@switches [paths: :keep, exemptions_file: :string]`, `@default_paths ["lib"]`
     - **Lines 15–39**: `run/1` loads exemptions via `load_exemptions/1`, delegates scanning to `SpecsCheck.missing_public_specs/2`, prints violations to `Mix.shell().error/1`, or raises `Mix.raise/1`.
     - **Lines 41–52**: `load_exemptions/1` reads exemptions file, filters blank lines and `#` comments, returning a `MapSet`.
   - **Engine Path**: `elixir/lib/symphony_elixir/specs_check.ex` (176 lines total)
     - **Lines 4–10**: `@type finding :: %{file: String.t(), module: String.t(), name: atom(), arity: non_neg_integer(), line: pos_integer()}`
     - **Lines 12–23**: `@spec missing_public_specs([Path.t()], keyword()) :: [finding()]` collects `.ex` files via wildcard `Path.wildcard/1`, invokes AST parser `file_findings/2`, and sorts results.
     - **Lines 43–58**: `file_findings/2` parses source AST via `Code.string_to_quoted(source, columns: true, file: file)` and extracts `module_nodes/1`.
     - **Lines 73–80**: `find_missing_specs/4` normalizes block forms and reduces forms using `initial_state/0` accumulator (`%{pending_specs: MapSet.new(), pending_impl: false, seen_defs: MapSet.new(), findings: []}`).
     - **Lines 86–138**: `consume_form/5` tracks `@spec` declarations, `@impl` attributes, `def` public functions, multi-clause function heads (tracked in `seen_defs`), and resets state on `defp` or other forms.

6. **Contextual Helper: `Mix.Tasks.Workspace.BeforeRemove`**
   - **Path**: `elixir/lib/mix/tasks/workspace.before_remove.ex` (141 lines total)
   - **Line 18**: `@default_repo "openai/symphony"`
   - **Lines 21–41**: `run/1` options parser accepting `--branch <name>`, `--repo <name>`, `--help`.
   - **Lines 45–53**: `maybe_close_open_pull_requests/2` checks `gh_available?()` and `gh_authenticated?()`, queries open PRs via `gh pr list`, and closes them via `gh pr close` before workspace deletion.

---

## 2. Logic Chain

### 2.1 Requirements Reconcilation & Section Hierarchy

To ensure 100% compliance with both the `ORIGINAL_REQUEST.md` (R1-R3), `PROJECT.md` milestones, and existing project documentation standards (`docs/01_` through `docs/07_`), the section hierarchy is organized into 5 major numbered sections:

```
# Symphony Utilities & Custom Mix Tasks Architecture

## 1. Overview & Architectural Role
   ├── 1.1 Scope and Subsystem Catalog
   └── 1.2 Architectural Roles & System Overview Diagram

## 2. Web Error Views
   ├── 2.1 HTML Error Handling (SymphonyElixirWeb.ErrorHTML)
   └── 2.2 JSON REST API Error Formatting (SymphonyElixirWeb.ErrorJSON)

## 3. Logging Infrastructure
   ├── 3.1 OTP Logger Disk Rotation Architecture (SymphonyElixir.LogFile)
   ├── 3.2 Configuration Parameters & Defaults
   └── 3.3 Console Logger Suppression Mechanics

## 4. Custom Mix Tasks & Quality Enforcement
   ├── 4.1 Pull Request Body Validator (mix pr_body.check)
   ├── 4.2 Code Spec Compliance Checker (mix specs.check & SymphonyElixir.SpecsCheck)
   └── 4.3 Workspace Teardown Helper (mix workspace.before_remove)

## 5. Integration Summary & Verification Matrix
   ├── 5.1 Component Capability & Trigger Matrix
   └── 5.2 Verification and Test Commands
```

### 2.2 Target Module & Subsystem Mapping Table

| Section # | Document Section Title | Target Elixir Module(s) | Source File Path | Line Range | Key Responsibilities & Functions |
|---|---|---|---|---|---|
| **1.1** | Subsystem Catalog | All 5 Target + 2 Helper Modules | All paths | 1–217 | Subsystem inventory table & architectural overview |
| **1.2** | System Overview Diagram | All Modules | All paths | - | Embeds **Diagram A (Subsystems Overview Flowchart)** |
| **2.1** | HTML Error Handling | `SymphonyElixirWeb.ErrorHTML` | `elixir/lib/symphony_elixir_web/error_html.ex` | 1–9 | HTML error rendering via `Phoenix.Controller.status_message_from_template/1` |
| **2.2** | JSON Error Formatting | `SymphonyElixirWeb.ErrorJSON` | `elixir/lib/symphony_elixir_web/error_json.ex` | 1–9 | REST API JSON error formatting (`%{error: %{code: "request_failed", message: ...}}`) |
| **3.1** | Disk Rotation Architecture | `SymphonyElixir.LogFile` | `elixir/lib/symphony_elixir/log_file.ex` | 1–81 | `:logger_disk_log_h` setup, `:wrap` mode, single-line formatter |
| **3.2** | Config Parameters | `SymphonyElixir.LogFile` | `elixir/lib/symphony_elixir/log_file.ex` | 8–30 | Application env defaults (`:log_file`, `max_bytes`, `max_files`) |
| **3.3** | Console Suppression | `SymphonyElixir.LogFile` | `elixir/lib/symphony_elixir/log_file.ex` | 60–66 | Removal of `:default` console logger for ANSI terminal safety (Embeds **Diagram D**) |
| **4.1** | PR Body Validator | `Mix.Tasks.PrBody.Check` | `elixir/lib/mix/tasks/pr_body.check.ex` | 1–217 | CI/CD markdown template linting, heading order, comments, checkboxes (Embeds **Diagram C**) |
| **4.2** | Spec Compliance Checker | `Mix.Tasks.Specs.Check` & `SymphonyElixir.SpecsCheck` | `elixir/lib/mix/tasks/specs.check.ex`, `elixir/lib/symphony_elixir/specs_check.ex` | 1–54, 1–176 | AST parsing via `Code.string_to_quoted`, form accumulator state machine (Embeds **Diagram B**) |
| **4.3** | Workspace Teardown Helper | `Mix.Tasks.Workspace.BeforeRemove` | `elixir/lib/mix/tasks/workspace.before_remove.ex` | 1–141 | Pre-deletion branch cleanup, GitHub CLI integration (`gh pr list`, `gh pr close`) |
| **5.1** | Component Capability Matrix | All Modules | All paths | - | Full matrix detailing triggers, inputs, outputs, failure modes |
| **5.2** | Verification Commands | All Modules | All paths | - | Exact shell commands to execute and verify each task/utility |

### 2.3 Mermaid Diagrams Assignment

Four distinct Mermaid diagrams are allocated to specific subsections:

1. **Diagram A (Utility Subsystems Architecture Overview)** -> Allocated to **Section 1.2**
   - *Type*: `flowchart TD`
   - *Purpose*: Shows high-level interaction of Web Error Views, Log File Handler, and CI/CD Mix Tasks within Symphony.
2. **Diagram B (`Specs.Check` AST Parsing Pipeline)** -> Allocated to **Section 4.2**
   - *Type*: `flowchart TD`
   - *Purpose*: Illustrates state machine traversal (`pending_specs`, `pending_impl`, `seen_defs`, exemptions check).
3. **Diagram C (`PrBody.Check` Validation Flowchart)** -> Allocated to **Section 4.1**
   - *Type*: `flowchart TD`
   - *Purpose*: Depicts options parsing, template reading, heading extraction, and 4-step linting pipeline.
4. **Diagram D (`LogFile` Rotation & Console Suppression Flow)** -> Allocated to **Section 3.3**
   - *Type*: `flowchart LR`
   - *Purpose*: Shows path expansion, directory creation, handler replacement, and console logger removal.

---

## 3. Implementation Plan for Worker Agent

The drafting of `docs/08_utilities_and_mix_tasks.md` shall be executed by the worker agent in 6 structured phases:

### Phase 1: Header, Executive Summary & Section 1 (Overview)
- **Action**: Create `docs/08_utilities_and_mix_tasks.md`.
- **Content**:
  - Title: `# Symphony Utilities & Custom Mix Tasks Architecture`
  - Executive summary introducing the 5 target utility and Mix task modules.
  - Section 1.1: Catalog table listing Module, File Path, Domain, and Responsibilities.
  - Section 1.2: Architectural overview prose and **Diagram A (`flowchart TD`)**.

### Phase 2: Section 2 (Web Error Views)
- **Action**: Draft Section 2 detailing Phoenix error views.
- **Content**:
  - Section 2.1: `SymphonyElixirWeb.ErrorHTML` (`error_html.ex`). Explain `render/2`, template status delegation via `Phoenix.Controller.status_message_from_template/1`, and code snippet.
  - Section 2.2: `SymphonyElixirWeb.ErrorJSON` (`error_json.ex`). Detail API error map schema (`%{error: %{code: "request_failed", message: ...}}`), REST endpoint integration under `/api/v1/*`, and code snippet.

### Phase 3: Section 3 (Application Logging Infrastructure)
- **Action**: Draft Section 3 detailing OTP disk logging and terminal UI protection.
- **Content**:
  - Section 3.1: `SymphonyElixir.LogFile` (`log_file.ex`). Explain `:logger_disk_log_h` setup, `:wrap` mode, single-line formatter, and disk rotation.
  - Section 3.2: Configuration parameters table (`:log_file`, `:log_file_max_bytes`, `:log_file_max_files`), defaults (10MB, 5 files), and environment overrides.
  - Section 3.3: Console logger suppression mechanics. Explain why `:logger.remove_handler(:default)` is invoked upon successful disk log setup to protect the ANSI `StatusDashboard` from stdout corruption. Embed **Diagram D (`flowchart LR`)**.

### Phase 4: Section 4 (Custom Mix Tasks & Quality Enforcement)
- **Action**: Draft Section 4 deep dives for all 3 Mix tasks and helper engine.
- **Content**:
  - Section 4.1: `Mix.Tasks.PrBody.Check` (`pr_body.check.ex`). Describe CLI flags (`--file`, `--help`), candidate template resolution (`.github/pull_request_template.md`), heading extraction regex (`~r/^\#{4,6}\s+.+$/m`), and 4-step linting pipeline (required headings, order, HTML comments, bullets/checkboxes). Embed **Diagram C (`flowchart TD`)**.
  - Section 4.2: `Mix.Tasks.Specs.Check` (`specs.check.ex`) and `SymphonyElixir.SpecsCheck` (`specs_check.ex`). Detail AST parsing algorithm via `Code.string_to_quoted/2`, state accumulator (`pending_specs`, `pending_impl`, `seen_defs`), `@impl` compliance, exemptions file parsing, and error reporting. Embed **Diagram B (`flowchart TD`)**.
  - Section 4.3: `Mix.Tasks.Workspace.BeforeRemove` (`workspace.before_remove.ex`). Document workspace teardown hook, GitHub CLI (`gh`) integration (`gh pr list`, `gh pr close`), CLI flags (`--branch`, `--repo`), and fallback behavior.

### Phase 5: Section 5 (Integration Summary & Component Matrix)
- **Action**: Draft Section 5 summary tables and verification commands.
- **Content**:
  - Section 5.1: Subsystem capability & trigger matrix summarizing all 7 modules.
  - Section 5.2: Verification and test commands suite.

### Phase 6: Quality Verification & Formatting Alignment
- **Action**: Validate document formatting, header levels, table borders, and Mermaid syntax.
- **Verification Commands**:
  - Check file exists at `docs/08_utilities_and_mix_tasks.md`.
  - Validate all 5 key target modules are present in text.
  - Run `mix specs.check` and `mix pr_body.check --help` in `elixir/`.

---

## 4. Caveats

No caveats. All 5 primary target modules (`error_html.ex`, `error_json.ex`, `log_file.ex`, `pr_body.check.ex`, `specs.check.ex`) and 2 helper modules (`specs_check.ex`, `workspace.before_remove.ex`) were directly verified from source code files in `elixir/lib/`.

---

## 5. Conclusion

The structural blueprint and implementation plan for `docs/08_utilities_and_mix_tasks.md` are fully defined and ready for execution. The document will seamlessly complete Symphony's 100% documentation coverage goal while adhering strictly to existing project standards (`docs/01_` through `docs/07_`).

---

## 6. Verification Method

### 6.1 Report Verification
1. Inspect `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_m1_1/handoff.md` to verify all 5 major sections, 4 Mermaid diagrams, module mappings, and implementation plan phases are present.

### 6.2 Codebase Verification Commands
```bash
# Verify source files exist in elixir repository
test -f /home/will/Projects/symphony/elixir/lib/symphony_elixir_web/error_html.ex
test -f /home/will/Projects/symphony/elixir/lib/symphony_elixir_web/error_json.ex
test -f /home/will/Projects/symphony/elixir/lib/symphony_elixir/log_file.ex
test -f /home/will/Projects/symphony/elixir/lib/mix/tasks/pr_body.check.ex
test -f /home/will/Projects/symphony/elixir/lib/mix/tasks/specs.check.ex
test -f /home/will/Projects/symphony/elixir/lib/symphony_elixir/specs_check.ex
test -f /home/will/Projects/symphony/elixir/lib/mix/tasks/workspace.before_remove.ex

# Verify execution of Mix tasks in elixir directory
cd /home/will/Projects/symphony/elixir
mix specs.check
mix pr_body.check --help
```
