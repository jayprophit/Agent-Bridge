# ADR-002: Keep the flat tests/ directory in v0.8.x

Status: accepted.

Context: 58 test files run under one discovery command
(`python -m unittest discover -s tests -p "test_*.py"`). Several suites
depend on CWD-relative fixtures (configs, UI dir, disposable temp dirs).

Decision: do NOT split into unit/integration/e2e/… subdirectories now.
Fragmentation would churn every suite for navigational taste only.

Consequences: use file-name prefixes and the release index for
navigation. Revisit when the suite outgrows single-command discovery.
