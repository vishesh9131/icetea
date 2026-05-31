# Icetea monorepo dev wrapper.
#
# Picks up backend at backend/ and frontend at frontend/. Backend assumes
# the venv at ../venv exists (the repo-root venv from the legacy layout)
# OR backend/.venv. Set BACKEND_PY to override the python interpreter.

ROOT       := $(abspath $(dir $(MAKEFILE_LIST)))
BACKEND    := $(ROOT)/backend
FRONTEND   := $(ROOT)/frontend

# Use the first python interpreter we can find: explicit override > backend
# venv > repo-root venv > system python3.
BACKEND_PY ?= $(shell \
  if [ -x "$(BACKEND)/.venv/bin/python" ]; then \
    echo "$(BACKEND)/.venv/bin/python"; \
  elif [ -x "$(ROOT)/venv/bin/python" ]; then \
    echo "$(ROOT)/venv/bin/python"; \
  else \
    command -v python3; \
  fi)

UVICORN    := $(BACKEND_PY) -m uvicorn icetea.api.app:app --host 127.0.0.1 --port 8000

.PHONY: help install dev backend frontend test test-fast harness harness-c build netlify-build clean kill

help:
	@echo "icetea — monorepo wrapper"
	@echo ""
	@echo "  make install      install backend + frontend deps"
	@echo "  make dev          backend + frontend together (Ctrl-C kills both)"
	@echo "  make backend      backend only (uvicorn on :8000)"
	@echo "  make frontend     frontend only (vite on :5173)"
	@echo "  make test         backend pytest"
	@echo "  make test-fast    backend pytest -x (stop on first failure)"
	@echo "  make harness      79 e2e scenarios, sequential"
	@echo "  make harness-c    79 e2e scenarios, --concurrency 4"
	@echo "  make build        frontend production build"
	@echo "  make netlify-build landing + terminal + dist/ for unified Netlify"
	@echo "  make clean        node_modules, dist, pycache, harness logs"
	@echo "  make kill         kill any uvicorn/vite on :8000/:5173"
	@echo ""
	@echo "BACKEND_PY=$(BACKEND_PY)"

install:
	@echo ">> backend deps"
	cd $(BACKEND) && $(BACKEND_PY) -m pip install -r requirements.txt
	@echo ">> frontend deps"
	cd $(FRONTEND) && npm install --no-audit --no-fund

dev:
	@trap 'kill 0' EXIT INT; \
	$(MAKE) backend & \
	$(MAKE) frontend & \
	wait

backend:
	cd $(BACKEND) && PYTHONPATH=. $(UVICORN) --log-level info

frontend:
	cd $(FRONTEND) && npm run dev

test:
	cd $(BACKEND) && APP_ENV=test PYTHONPATH=. $(BACKEND_PY) -m pytest tests/ -q --tb=short

test-fast:
	cd $(BACKEND) && APP_ENV=test PYTHONPATH=. $(BACKEND_PY) -m pytest tests/ -q --tb=short -x

harness:
	cd $(BACKEND) && PYTHONPATH=. $(BACKEND_PY) -u -m scripts.harness.run

harness-c:
	cd $(BACKEND) && PYTHONPATH=. $(BACKEND_PY) -u -m scripts.harness.run --concurrency 4

build:
	cd $(FRONTEND) && npm run build

netlify-build:
	bash $(ROOT)/scripts/build-netlify-unified.sh

clean:
	@echo ">> frontend"
	rm -rf $(FRONTEND)/dist $(FRONTEND)/node_modules/.vite
	@echo ">> backend caches"
	find $(BACKEND) -type d \( -name __pycache__ -o -name .pytest_cache \) -prune -exec rm -rf {} +
	@echo ">> harness logs"
	rm -rf $(BACKEND)/Logs/harness $(BACKEND)/Logs/memory

kill:
	-lsof -ti:8000 2>/dev/null | xargs -r kill -9 2>/dev/null || true
	-lsof -ti:5173 2>/dev/null | xargs -r kill -9 2>/dev/null || true
	@echo "killed uvicorn :8000 + vite :5173 (if running)"
