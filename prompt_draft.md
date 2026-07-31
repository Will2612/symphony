# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview

Comprehensively investigate the codebase, draw diagrams to explain its contents, breaking it down by business domain/feature, and generating specific documentation for each core module.

Working directory: /home/will/Projects/symphony
Integrity mode: development

## Requirements

### R1. Repository Analysis
Analyze the repository to understand its overall architecture, key components, and core business domains. 

### R2. Documentation Generation
Generate detailed Markdown documentation. The output should be placed in a `docs/` directory within the project. It should include an overall system overview, as well as separate, dedicated documents for each core business domain or module.

### R3. Diagram Creation
Embed Mermaid diagrams within the Markdown documentation. Specifically, generate:
1. An overall system architecture diagram.
2. Module dependency or class diagrams for each core domain.
3. Sequence diagrams illustrating the core business flows.

## Acceptance Criteria

### Verification
- [ ] A `docs/` directory is created in the repository root.
- [ ] The `docs/` directory contains an overall overview document and multiple domain-specific documents.
- [ ] Every document contains at least one Mermaid diagram block.
- [ ] All Mermaid diagrams possess valid syntax and can be rendered without errors.
- [ ] The documentation accurately reflects the current state and structure of the provided codebase.

---
*Next: when approved → delegate via invoke_subagent (see Delegation Protocol)*
