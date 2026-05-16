.PHONY: help venv install storage-dirs db-init db-schema run clean

PYTHON ?= python3
VENV ?= .venv
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn

help:
	@echo "Available targets:"
	@echo "  make venv       Create the Python virtual environment"
	@echo "  make install    Create .venv and install requirements"
	@echo "  make storage-dirs Create local storage directories"
	@echo "  make db-init    Create/update local PostgreSQL database and schema"
	@echo "  make db-schema  Apply sql/schema.sql to the configured database"
	@echo "  make run        Start the FastAPI development server"
	@echo "  make clean      Remove Python cache files"

venv:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip

install: venv storage-dirs
	$(PIP) install -r requirements.txt

storage-dirs:
	mkdir -p storage/wads storage/analysis storage/reports storage/recordings storage/screenshots

db-init:
	bash scripts/init_db.sh

db-schema:
	. ./.env && PGPASSWORD="$$POSTGRES_PASSWORD" psql \
		--host "$$POSTGRES_HOST" \
		--port "$$POSTGRES_PORT" \
		--username "$$POSTGRES_USER" \
		--dbname "$$POSTGRES_DB" \
		--file sql/schema.sql \
		--set ON_ERROR_STOP=1

run:
	$(UVICORN) app.main:app --reload --host 0.0.0.0 --port 8000

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
