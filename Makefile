.PHONY: help install sync lint format typecheck test run clean docker-build docker-run

PYTHON := python
UV := python -m uv

help:
	@echo "ApexPrice Engine - Comandos de Automação:"
	@echo "  make install     Instala dependências completas com uv"
	@echo "  make lint        Executa ruff check"
	@echo "  make format      Formata código com ruff format"
	@echo "  make typecheck   Verifica tipagem com mypy"
	@echo "  make test        Executa testes automatizados com pytest e coverage"
	@echo "  make run         Executa o pipeline principal CLI"
	@echo "  make gui         Inicia a interface gráfica desktop CustomTkinter"
	@echo "  make build-exe   Compila a aplicação num executável .exe único com PyInstaller"
	@echo "  make clean       Limpa caches e arquivos temporários"

install:
	$(UV) sync --all-extras

lint:
	$(UV) run ruff check .

format:
	$(UV) run ruff format .
	$(UV) run ruff check --fix .

typecheck:
	$(UV) run mypy config models database pipelines scrapers notifications gui

test:
	$(UV) run pytest -v --cov=. --cov-report=term-missing

run:
	$(UV) run python main.py --query "PlayStation 5" --retailer all

gui:
	$(UV) run python app_gui.py

build-exe:
	$(UV) run python build_exe.py

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache __pycache__ *.egg-info .coverage htmlcov data/*.db reports/*.xlsx build dist *.spec
