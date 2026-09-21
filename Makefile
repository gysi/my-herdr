# Local checks only; there is no CI. Standard library only, so no setup step.
PYTHON ?= python3

.PHONY: check test syntax manifest link logs

## everything that must pass before a commit
check: syntax manifest test

## unit + end-to-end tests (end-to-end run bin/my-herdr against tests/mocks/herdr)
test:
	$(PYTHON) -m unittest discover -s tests

## syntax gate. compileall only looks at *.py, so the extensionless entry
## point and the fake herdr CLI need py_compile by name.
syntax:
	$(PYTHON) -m compileall -q myherdr tests
	$(PYTHON) -m py_compile bin/my-herdr tests/mocks/herdr

## offline manifest validation (herdr plugin link is the authoritative one)
manifest:
	$(PYTHON) tests/check_manifest.py

## register this checkout with the running herdr; re-run after manifest edits
link:
	herdr plugin link .
	herdr plugin action list --plugin my-herdr

## what the last actions printed; the only place action output goes
logs:
	herdr plugin log list --plugin my-herdr --limit 5
