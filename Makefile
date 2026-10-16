.ONESHELL:
SHELL := /bin/bash

RM = rm -fr

VENV_DIR := .venv
PYTHON := python3
PIP := pip
C_DIR := pwd

UV := $(shell command -v uv 2>/dev/null)

# ARGS := $(wordlist 2, 999, $(MAKECMDGOALS))

define ACTIVATE_VENV
if [ -z "$$VIRTUAL_ENV" ]; then \
	echo "No virtual environment detected."; \
	$(MAKE) venv; \
	. "$(VENV_DIR)/bin/activate"; \
fi
endef


help:
	uv run python -m src --help

install:
#	mkdir -p .cache/uv_cache .cache/hf_cache
#	UV_CACHE_DIR=.cache/uv_cache \ 
#	HF_HOME=.cache/hf_cache \ 

	uv sync --python 3

run:
	# uv run python -m src $(ACOMMAND) $(ARGS)
	# uv run python -m src

	uv run python -m agent_mbpp --task-file cache/mbpp_task.json \
		--output cache/mbpp_solution.json \
		--model-name "openrouter/free" \
		--provider-url "https://openrouter.ai/api/v1" \
#		--provider-api-keys-file "cache/mbpp_task.json" 
# 		--provider-api-key "1 zsdfsd" \
# 		--provider-api-key "2 zsdfsd"


debug:
	uv run python -m pdb -m src


check-venv:
	@if [ -z "$$VIRTUAL_ENV" ]; then \
		echo "No virtual environment detected."; \
		$(MAKE) venv; \
		. "$(VENV_DIR)/bin/activate"; \
		echo "Virtual environment in $(VENV_DIR)."; \
	else \
		echo "Using virtual environment: $$VIRTUAL_ENV"; \
	fi

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating virtual environment..."; \
		make install \
		chmod +x "$(VENV_DIR)/bin/activate" ; \
	else \
		echo "Virtual environment already exists."; \
	fi

clean:
	@$(RM) .mypy_cache
	@$(RM) __pycache__
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name .mypy_cache -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	find . -name .pytest_cache -exec rm -rf {} +
	find . -name .ruff_cache -exec rm -rf {} +
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete
	@$(RM) data/cache/

fclean: clean
	@$(RM) .cache
	@$(RM) .venv

lint:
	uv run flake8 src/*.py agent_mbpp.py
	uv run mypy src/ --warn-return-any \
	--warn-unused-ignores \
	--ignore-missing-imports \
	--disallow-untyped-defs \
	--check-untyped-defs \
	--follow-imports=silent

lint-strict: 
	uv run flake8 src/*.py
	uv run mypy src/ --strict --follow-imports=silent


.PHONY: install run debug clean lint lint-strict fclean runapi check-venv venv

#  ln -s ~/goinfre/uv uv
