import os
import re
import sys

DOCS_DIR = "/home/will/Projects/symphony/docs"
ELIXIR_LIB_DIR = "/home/will/Projects/symphony/elixir/lib"

doc_files = sorted([f for f in os.listdir(DOCS_DIR) if f.startswith("0") and f.endswith(".md")])

print(f"Found {len(doc_files)} domain documentation files in {DOCS_DIR}:")
for df in doc_files:
    print(f" - {df}")

# Collect all Elixir modules in elixir/lib
elixir_modules = set()
for root, _, files in os.walk(ELIXIR_LIB_DIR):
    for file in files:
        if file.endswith(".ex"):
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                # Find defmodule Module.Name
                matches = re.findall(r'defmodule\s+([A-Z][A-Za-z0-9_.]*)', content)
                for m in matches:
                    elixir_modules.add(m)

print(f"\nDiscovered {len(elixir_modules)} defined Elixir modules in codebase:")
for mod in sorted(elixir_modules):
    print(f"  * {mod}")

print("\n--- AUDITING DOC FILES ---")

total_diagrams = 0
file_diagram_counts = {}
placeholders_found = []
module_references = {}
invalid_diagrams = []

placeholder_patterns = [
    r'\bTODO\b', r'\bTBD\b', r'\bFIXME\b', r'\[Placeholder\]', r'\[Insert\s+.*\]',
    r'\bFoo\b', r'\bBar\b', r'\bBaz\b', r'xxx', r'your_module_here'
]

for df in doc_files:
    filepath = os.path.join(DOCS_DIR, df)
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Check for placeholders
    for pat in placeholder_patterns:
        matches = re.findall(pat, content, re.IGNORECASE)
        if matches:
            placeholders_found.append((df, pat, matches))

    # Find mermaid blocks
    mermaid_blocks = re.findall(r'```mermaid\s*\n(.*?)\n```', content, re.DOTALL)
    file_diagram_counts[df] = len(mermaid_blocks)
    total_diagrams += len(mermaid_blocks)

    # Check mermaid block validity & modules
    for i, block in enumerate(mermaid_blocks, 1):
        lines = block.strip().split('\n')
        if not lines or not lines[0].strip():
            invalid_diagrams.append((df, i, "Empty mermaid block"))
            continue
        
        first_line = lines[0].strip()
        valid_types = ['graph', 'flowchart', 'sequenceDiagram', 'classDiagram', 'stateDiagram-v2', 'stateDiagram', 'erDiagram', 'gantt', 'pie', 'gitGraph']
        if not any(first_line.startswith(vt) for vt in valid_types):
            invalid_diagrams.append((df, i, f"Unknown diagram type: {first_line}"))

        # Check for unclosed brackets or syntax errors in block
        open_parens = block.count('(') - block.count(')')
        open_brackets = block.count('[') - block.count(']')
        open_braces = block.count('{') - block.count('}')
        if open_parens != 0 or open_brackets != 0 or open_braces != 0:
            invalid_diagrams.append((df, i, f"Unbalanced brackets in diagram: ()={open_parens}, []={open_brackets}, {{}}={open_braces}"))

    # Extract Elixir module mentions
    mods_in_doc = set(re.findall(r'SymphonyElixir[A-Za-z0-9_.]*', content))
    module_references[df] = mods_in_doc

print(f"\nTotal Mermaid diagrams found: {total_diagrams}")
for df, count in file_diagram_counts.items():
    print(f"  - {df}: {count} diagrams")

print(f"\nPlaceholder check: {'FAIL' if placeholders_found else 'PASS'}")
if placeholders_found:
    for item in placeholders_found:
        print(f"  WARNING: Placeholder in {item[0]}: pattern {item[1]} matched {item[2]}")

print(f"\nMermaid diagram syntax check: {'FAIL' if invalid_diagrams else 'PASS'}")
if invalid_diagrams:
    for item in invalid_diagrams:
        print(f"  ERROR in {item[0]} diagram #{item[1]}: {item[2]}")

print("\nModule reference check against codebase:")
all_doc_mods = set()
for df, mods in module_references.items():
    all_doc_mods.update(mods)

missing_mods = []
for mod in sorted(all_doc_mods):
    clean_mod = mod.rstrip('.')
    if clean_mod not in elixir_modules:
        missing_mods.append(clean_mod)

if missing_mods:
    print(f"  WARNING/FAIL: Referenced modules not found in codebase: {missing_mods}")
else:
    print("  PASS: All referenced SymphonyElixir modules exist in elixir/lib!")

