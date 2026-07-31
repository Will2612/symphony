# Handoff Report: Elixir Utility Modules Technical Survey

**Author Agent**: `teamwork_preview_explorer_survey_1`  
**Working Directory**: `/home/will/Projects/symphony/.agents/teamwork_preview_explorer_survey_1`  
**Target Project Directory**: `/home/will/Projects/symphony`  
**Target Modules Analyzed**:
1. `SymphonyElixirWeb.ErrorHTML` (`elixir/lib/symphony_elixir_web/error_html.ex`)
2. `SymphonyElixirWeb.ErrorJSON` (`elixir/lib/symphony_elixir_web/error_json.ex`)
3. `SymphonyElixir.LogFile` (`elixir/lib/symphony_elixir/log_file.ex`)

---

## 1. Observation

### Target Module 1: `SymphonyElixirWeb.ErrorHTML`
- **File Location**: `elixir/lib/symphony_elixir_web/error_html.ex` (Lines 1–9)
- **Module Name**: `SymphonyElixirWeb.ErrorHTML`
- **Annotations**: `@moduledoc false`
- **Source Code**:
  ```elixir
  defmodule SymphonyElixirWeb.ErrorHTML do
    @moduledoc false

    @spec render(String.t(), map()) :: String.t()
    def render(template, _assigns) do
      Phoenix.Controller.status_message_from_template(template)
    end
  end
  ```
- **Configuration Site**: `elixir/config/config.exs:8-11`:
  ```elixir
  config :symphony_elixir, SymphonyElixirWeb.Endpoint,
    render_errors: [
      formats: [html: SymphonyElixirWeb.ErrorHTML, json: SymphonyElixirWeb.ErrorJSON],
      layout: false
    ]
  ```
- **Specs Exclusion Site**: `elixir/mix.exs:31`: Listed in `ignore_modules` under `specs_check` config.
- **Test File**: No dedicated test file found in `elixir/test/`. Framework error rendering is delegated to Phoenix Endpoint configuration.

---

### Target Module 2: `SymphonyElixirWeb.ErrorJSON`
- **File Location**: `elixir/lib/symphony_elixir_web/error_json.ex` (Lines 1–9)
- **Module Name**: `SymphonyElixirWeb.ErrorJSON`
- **Annotations**: `@moduledoc false`
- **Source Code**:
  ```elixir
  defmodule SymphonyElixirWeb.ErrorJSON do
    @moduledoc false

    @spec render(String.t(), map()) :: map()
    def render(template, _assigns) do
      %{error: %{code: "request_failed", message: Phoenix.Controller.status_message_from_template(template)}}
    end
  end
  ```
- **Configuration Site**: `elixir/config/config.exs:8-11` (configured alongside `ErrorHTML`).
- **Specs Exclusion Site**: `elixir/mix.exs:32`: Listed in `ignore_modules` under `specs_check` config.
- **Test File**: No dedicated test file found in `elixir/test/`.

---

### Target Module 3: `SymphonyElixir.LogFile`
- **File Location**: `elixir/lib/symphony_elixir/log_file.ex` (Lines 1–81)
- **Module Name**: `SymphonyElixir.LogFile`
- **Moduledoc**: `"Configures OTP's built-in rotating disk log handler for application logs."`
- **Module Constants & Default Values**:
  - `@handler_id :symphony_disk_log`
  - `@default_log_relative_path "log/symphony.log"`
  - `@default_max_bytes 10 * 1024 * 1024` (10 MB = 10,485,760 bytes)
  - `@default_max_files 5`
- **Function Signatures & Specs**:
  1. `default_log_file/0`: `@spec default_log_file() :: Path.t()`
     - Body: `default_log_file(File.cwd!())`
  2. `default_log_file/1`: `@spec default_log_file(Path.t()) :: Path.t()`
     - Guard: `when is_binary(logs_root)`
     - Body: `Path.join(logs_root, @default_log_relative_path)`
  3. `configure/0`: `@spec configure() :: :ok`
     - Environment lookup keys:
       - `:log_file` (fallback: `default_log_file()`)
       - `:log_file_max_bytes` (fallback: `@default_max_bytes`)
       - `:log_file_max_files` (fallback: `@default_max_files`)
     - Workflow: Expands path, creates parent directory (`File.mkdir_p/1`), removes existing handler (`:logger.remove_handler(:symphony_disk_log)`), registers handler (`:logger.add_handler(:symphony_disk_log, :logger_disk_log_h, config)`), removes default console handler (`:logger.remove_handler(:default)`).
- **Disk Handler Configuration Structure**:
  ```elixir
  %{
    level: :all,
    formatter: {:logger_formatter, %{single_line: true}},
    config: %{
      file: String.to_charlist(path), # Converts binary string to Erlang charlist
      type: :wrap,                    # Rotating file mode
      max_no_bytes: max_bytes,        # 10 MB per file by default
      max_no_files: max_files         # 5 rotated files by default
    }
  }
  ```
- **Call Sites & Lifecycle Wiring**:
  1. `elixir/lib/symphony_elixir.ex:24`: `SymphonyElixir.Application.start/2` calls `:ok = SymphonyElixir.LogFile.configure()` before starting supervisor children.
  2. `elixir/lib/symphony_elixir/cli.ex:147`: `set_logs_root/1` sets `Application.put_env(:symphony_elixir, :log_file, LogFile.default_log_file(logs_root))` when CLI initializes.
- **Specs Exclusion Site**: `elixir/mix.exs:27`: Listed in `ignore_modules` under `specs_check`.
- **Test File**: `elixir/test/symphony_elixir/log_file_test.exs` (Lines 1–14):
  ```elixir
  defmodule SymphonyElixir.LogFileTest do
    use ExUnit.Case, async: true
    alias SymphonyElixir.LogFile

    test "default_log_file/0 uses the current working directory" do
      assert LogFile.default_log_file() == Path.join(File.cwd!(), "log/symphony.log")
    end

    test "default_log_file/1 builds the log path under a custom root" do
      assert LogFile.default_log_file("/tmp/symphony-logs") == "/tmp/symphony-logs/log/symphony.log"
    end
  end
  ```

---

## 2. Logic Chain

1. **HTML & JSON Error View Architecture**:
   - `SymphonyElixirWeb.Endpoint` delegates HTTP error response rendering to `SymphonyElixirWeb.ErrorHTML` (for HTML requests) and `SymphonyElixirWeb.ErrorJSON` (for JSON API requests) based on format negotiated by Phoenix.
   - `ErrorHTML.render/2` takes template names like `"404.html"` or `"500.html"`, extracts status reason phrases (e.g., `"Not Found"`, `"Internal Server Error"`) via `Phoenix.Controller.status_message_from_template/1`, and returns plain binary text strings.
   - `ErrorJSON.render/2` takes template names like `"404.json"`, extracts status reason phrases via the same helper, and constructs a structured payload: `%{error: %{code: "request_failed", message: "<reason_phrase>"}}`. Phoenix serializes this map to JSON via Jason encoder.

2. **OTP Rotating Disk Logger Architecture**:
   - `SymphonyElixir.LogFile` abstracts Erlang/OTP `:logger` configuration to store single-line formatted logs in a rotating set of files.
   - During OTP application startup (`SymphonyElixir.Application.start/2`), `LogFile.configure()` runs synchronously before any worker or supervisor is started.
   - If the CLI specifies a custom log root directory, `CLI.set_logs_root/1` updates application environment variable `:log_file` prior to starting the application tree.
   - `setup_disk_handler/3` converts the file path string to an Erlang charlist (`String.to_charlist/1`), ensures the parent directory exists on disk, unregisters any existing `:symphony_disk_log` handler, adds the `:logger_disk_log_h` handler with level `:all` and `:wrap` log mode, and finally detaches the default stdout console handler `:default`.
   - Error handling is fault-tolerant: if `:logger.add_handler/3` fails, `LogFile` captures `{:error, reason}`, logs a warning via `Logger.warning/1`, and returns `:ok` to prevent startup crash.

---

## 3. Caveats

1. **Interactive Test Execution**: The shell tool execution for `mix test` timed out waiting for user confirmation in read-only environment. All observations were verified via direct source code examination, static analysis, and existing ExUnit test file inspection (`elixir/test/symphony_elixir/log_file_test.exs`).
2. **Framework Integration Tests**: `ErrorHTML` and `ErrorJSON` do not have dedicated unit tests in `elixir/test/`, as they are standard Phoenix error views tested implicitly through Phoenix framework endpoint behavior.
3. **Erlang Type Conversion**: Note that `:logger_disk_log_h` requires file paths to be Erlang charlists (`String.to_charlist/1`). Passing Elixir UTF-8 binaries directly to `:logger_disk_log_h` would fail at Erlang runtime.

---

## 4. Conclusion

All 3 modules are concise, single-responsibility utilities in the Symphony Elixir architecture:
- `ErrorHTML` & `ErrorJSON` form the web layer's HTTP error presentation boundary, returning clean, unified error responses for HTML and JSON endpoints.
- `LogFile` forms the core system logging layer, configuring Erlang OTP's built-in `:logger_disk_log_h` rotating log handler with 10MB chunk rotation and a maximum of 5 log archives.

These details provide complete, exact, line-referenced documentation requirements for the technical author building `docs/08_utilities_and_mix_tasks.md`.

---

## 5. Verification Method

To verify these findings independently:

1. **Inspect Module Definitions**:
   ```bash
   view_file elixir/lib/symphony_elixir_web/error_html.ex
   view_file elixir/lib/symphony_elixir_web/error_json.ex
   view_file elixir/lib/symphony_elixir/log_file.ex
   ```
2. **Inspect Configuration & Application Wiring**:
   ```bash
   grep_search Query: "ErrorHTML" SearchPath: "elixir"
   grep_search Query: "LogFile" SearchPath: "elixir"
   ```
3. **Run Unit Tests**:
   ```bash
   mix test test/symphony_elixir/log_file_test.exs
   ```
4. **Invalidation Conditions**:
   - The analysis would be invalidated if `LogFile` handler ID, default log path (`"log/symphony.log"`), chunk size (10MB), or rotated file count (5) were altered in `log_file.ex`.
   - The error structure for `ErrorJSON` would be invalidated if the output key structure changes from `%{error: %{code: "request_failed", message: ...}}`.
