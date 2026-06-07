PYTHON := .venv/bin/python
PIP    := .venv/bin/pip

.PHONY: setup sample validate run-train run-test clean help

help:
	@echo "Alvos disponíveis:"
	@echo "  setup       Cria o ambiente virtual e instala dependências"
	@echo "  sample      Executa o pipeline na amostra de 20 linhas (requer Ollama)"
	@echo "  validate    Valida o arquivo sample-MGS-BR.csv gerado"
	@echo "  run-train   Processa o dataset de treino completo (requer ANTHROPIC_API_KEY)"
	@echo "  run-test    Processa o dataset de teste completo (requer ANTHROPIC_API_KEY)"
	@echo "  clean       Remove saídas geradas e checkpoints"

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip --quiet
	$(PIP) install -r requirements.txt --quiet
	@echo ""
	@echo "Pronto. Para ativar: source .venv/bin/activate"

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

# Datasets completos — requer chave de API configurada no ambiente
run-train: $(PYTHON)
	$(PYTHON) adapt_dataset.py --input train-MGS.csv --resume

run-test: $(PYTHON)
	$(PYTHON) adapt_dataset.py --input test-MGS.csv --resume

clean:
	rm -f dataset/sample-MGS-BR.csv dataset/train-MGS-BR.csv dataset/test-MGS-BR.csv
	rm -f dataset/adaptation-decisions.md
	rm -rf .checkpoints/

$(PYTHON):
	@echo "Ambiente virtual não encontrado. Execute primeiro: make setup"
	@exit 1
