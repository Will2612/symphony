# Master Plan — Project Symphony Documentation

## Mission & Requirements
- **R1 Repository Analysis**: Comprehensive codebase analysis to identify overall architecture, key components, data flow, and core business domains.
- **R2 Documentation Generation**: Write detailed Markdown docs in `docs/` (root overview document + domain/module specific documents).
- **R3 Diagram Creation**: Include valid Mermaid diagrams in every document (architecture, dependency, class, sequence diagrams).
- **Acceptance Criteria**:
  1. `docs/` created in root directory.
  2. Overall overview + multiple domain docs created.
  3. Every doc has >= 1 valid Mermaid diagram block.
  4. Documentation accurately reflects codebase.

## Phase 0: Survey & Architecture Discovery
- Spawn 3 parallel Explorers to analyze repository structure, dependencies, domain boundaries, entry points, configuration, and data pipelines.
- Merge findings into `PROJECT.md` Feature Inventory & Architecture breakdown.

## Phase 1: Milestone Decomposition & Test Infra Setup
- Define documentation milestones by core business module/domain.
- Establish document validation & Mermaid syntax verification checklist.

## Phase 2: Documentation Execution & Verification Loops
- For each documentation milestone:
  1. Explorer details domain specific interfaces, schemas, workflows.
  2. Worker writes/updates Markdown doc in `docs/` with Mermaid diagrams.
  3. Reviewer checks completeness, clarity, accuracy, formatting.
  4. Challenger/Auditor validates Mermaid diagram syntax and authenticity.
  5. Gate check: pass all checks or iterate.

## Phase 3: Final Acceptance & Reporting
- Verify all requirements R1-R3 and acceptance criteria.
- Present summary report to user.
