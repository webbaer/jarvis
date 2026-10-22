PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python3)

.PHONY: install api ui run test

install:
	$(PYTHON) -m pip install -e '.[dev,api,ui]'

api:
	$(PYTHON) -m api

ui:
	$(PYTHON) -m streamlit run ui/app.py

# API and UI side by side; Ctrl+C stops both.
run:
	$(MAKE) -j2 api ui

test:
	$(PYTHON) -m pytest -q
