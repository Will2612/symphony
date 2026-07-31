## 2026-07-31T21:57:56Z
You are teamwork_preview_test_writer for the E2E Testing Track. Your working directory is `/home/will/Projects/symphony/.agents/e2e_test_writer_1`.

MANDATORY: Read `/home/will/Projects/symphony/.agents/ORIGINAL_REQUEST.md` and `/home/will/Projects/symphony/PROJECT.md` first.

Your objective:
1. Create a comprehensive, executable E2E verification test suite (as an ExUnit test file `elixir/test/docs_08_verification_test.exs` or standalone executable script) that validates `docs/08_utilities_and_mix_tasks.md` against all user acceptance criteria and requirements:
   - File exists at `docs/08_utilities_and_mix_tasks.md`.
   - Contains sections for all 5 required modules (`SymphonyElixirWeb.ErrorHTML`, `SymphonyElixirWeb.ErrorJSON`, `SymphonyElixir.LogFile`, `Mix.Tasks.PrBody.Check`, `Mix.Tasks.Specs.Check`).
   - Contains at least 1 valid Mermaid diagram block (and tests diagram syntax blocks).
   - Validates heading structure, table contents, and key behavioral details (Tier 1 to Tier 4 test cases).
2. Run the test suite (expecting it to fail initially until the document is written).
3. Publish `TEST_READY.md` at `/home/will/Projects/symphony/TEST_READY.md` summarizing the test suite layout, test cases, and instructions for running it.
4. Write your completion report to `/home/will/Projects/symphony/.agents/e2e_test_writer_1/handoff.md` and send a message back.
