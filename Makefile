PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

.PHONY: setup setup-dev sample validate validate-all run-train run-test retry-failed test lint datacard status clean clean-all help

help:
	@echo "Alvos disponíveis:"
	@echo "  setup        Cria o ambiente virtual e instala dependências"
	@echo "  setup-dev    Como setup, mais dependências de desenvolvimento (pytest, ruff)"
	@echo "  sample       Executa o pipeline na amostra de 20 linhas (requer Ollama)"
	@echo "  validate     Valida o arquivo sample-MGS-BR.csv gerado"
	@echo "  validate-all Valida todos os dataset/*-MGS-BR.csv (exit 1 se houver erros)"
	@echo "  run-train    Processa o dataset de treino completo (requer ANTHROPIC_API_KEY)"
	@echo "  run-test     Processa o dataset de teste completo (requer ANTHROPIC_API_KEY)"
	@echo "  retry-failed Reprocessa linhas que ficaram sem tradução no treino"
	@echo "  test         Roda a suíte de testes (pytest)"
	@echo "  lint         Roda o ruff no pacote e nos testes"
	@echo "  datacard     Gera dataset/README.md a partir dos CSVs adaptados"
	@echo "  status       Mostra processo em background e progresso dos checkpoints"
	@echo "  clean        Remove saídas geradas (preserva checkpoints)"
	@echo "  clean-all    Remove saídas geradas E checkpoints (perde progresso de API)"

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip --quiet
	$(PIP) install -r requirements.txt --quiet
	@echo ""
	@echo "Pronto. Para ativar: source .venv/bin/activate"

setup-dev: setup
	$(PIP) install -r requirements-dev.txt --quiet

# Teste completo sem chave de API — requer Ollama rodando (https://ollama.com)
# Para usar outro modelo: make sample OLLAMA_MODEL=gemma3:4b
OLLAMA_MODEL ?= llama3.2:latest
sample: $(PYTHON)
	$(PYTHON) adapt_dataset.py \
		--provider ollama \
		--model $(OLLAMA_MODEL) \
		--input sample-MGS.csv \
		--batch-size 5
	$(PYTHON) validate_adapted.py dataset/sample-MGS-BR.csv

validate: $(PYTHON)
	$(PYTHON) validate_adapted.py dataset/sample-MGS-BR.csv

validate-all: $(PYTHON)
	$(PYTHON) validate_adapted.py --all

# Datasets completos — requer chave de API configurada no ambiente
run-train: $(PYTHON)
	$(PYTHON) adapt_dataset.py --input train-MGS.csv --resume

run-test: $(PYTHON)
	$(PYTHON) adapt_dataset.py --input test-MGS.csv --resume

retry-failed: $(PYTHON)
	$(PYTHON) adapt_dataset.py --input train-MGS.csv --retry-failed

test: $(PYTHON)
	$(PYTHON) -m pytest

lint: $(PYTHON)
	$(PYTHON) -m ruff check mgsbr tests adapt_dataset.py validate_adapted.py

datacard: $(PYTHON)
	$(PYTHON) -m mgsbr.datacard

status:
	@if [ -f logs/adapt.pid ] && kill -0 "$$(cat logs/adapt.pid)" 2>/dev/null; then \
		echo "Processo em execução (PID $$(cat logs/adapt.pid))"; \
	else \
		echo "Nenhum processo em background"; \
	fi
	@for f in .checkpoints/*_checkpoint.jsonl; do \
		[ -f "$$f" ] && echo "$$f: $$(wc -l < "$$f") linhas no checkpoint"; \
	done; true

clean:
	rm -f dataset/sample-MGS-BR.csv dataset/train-MGS-BR.csv dataset/test-MGS-BR.csv
	rm -f dataset/*-MGS-BR.parquet dataset/*-MGS-BR.run.json
	rm -f dataset/adaptation-decisions.md dataset/adaptation-decisions-*.md

# Checkpoints representam horas de API paga — só remova quando tiver certeza.
clean-all: clean
	rm -rf .checkpoints/

$(PYTHON):
	@echo "Ambiente virtual não encontrado. Execute primeiro: make setup"
	@exit 1
