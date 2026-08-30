.PHONY: check test

PYTHON ?= python3
export PYTHONDONTWRITEBYTECODE := 1

check: test
	$(PYTHON) -m compileall -q -f src tests
	git diff --check
	@test -z "$$(git status --porcelain --untracked-files=no)"

test:
	$(PYTHON) -m pytest -q
