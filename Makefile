VENV := .venv
PY := $(VENV)/bin/python

.PHONY: venv test run clean

venv:
	python3 -m venv $(VENV)
	$(PY) -m pip install -q -e '.[dev]'

test:
	$(PY) -m pytest -q

run:
	set -a && . ./.env && set +a && $(PY) -m commutehelper

clean:
	rm -rf $(VENV) *.egg-info
