# Makefile — audiolayers_gui
# Usa il Python del venv se presente, altrimenti quello di sistema.

ifeq ($(OS),Windows_NT)
    PYTHON := $(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,python)
else
    # In WSL il venv Windows è utilizzabile via interop (.exe): un solo venv
    # per entrambi i mondi. Un eventuale venv Linux nativo ha la precedenza.
    PYTHON := $(if $(wildcard .venv/bin/python),.venv/bin/python,$(if $(wildcard .venv/Scripts/python.exe),.venv/Scripts/python.exe,python3))
endif

.PHONY: tests test unit integration e2e install gui

tests: ## Suite completa
	$(PYTHON) -m pytest

test: tests

unit: ## Solo unit test
	$(PYTHON) -m pytest tests/unit

integration: ## Solo integration test
	$(PYTHON) -m pytest tests/integration

e2e: ## Solo end-to-end (server reale via subprocess)
	$(PYTHON) -m pytest tests/e2e -m e2e

install: ## Installa/aggiorna dipendenze nel venv
	$(PYTHON) -m pip install -r requirements.txt

gui: ## Avvia la GUI web su http://localhost:8000
	$(PYTHON) -m audiolayers_gui
