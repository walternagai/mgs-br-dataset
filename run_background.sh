#!/usr/bin/env bash
#
# Executa o script adapt_dataset.py em background com logging adequado.
#
# Pré-requisitos:
#   - Ambiente virtual configurado (make setup)
#   - Arquivo .env com as chaves de API (cp .env.example .env && edite)
#
# Uso:
#   ./run_background.sh [argumentos para adapt_dataset.py]
#
# Exemplos:
#   ./run_background.sh --provider ollama --model llama3.2:latest --input train-MGS.csv --resume --workers 2
#   ./run_background.sh --provider anthropic --input all --resume --workers 8
#   ./run_background.sh --provider groq --input train-MGS.csv --resume --workers 4 --verbose
#
# O script:
#   - Cria diretório logs/ se necessário
#   - Gera arquivo de log com timestamp (stdout/stderr bruto do nohup)
#   - O Python escreve logs estruturados em logs/adapt_dataset.log (nível DEBUG)
#   - Salva o PID em logs/adapt.pid
#   - Executa com nohup em background
#   - Mostra comandos para monitorar e parar o processo
#   - Ao receber SIGTERM/SIGINT, o Python salva o checkpoint antes de sair

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${SCRIPT_DIR}/.venv/bin/python"
LOGDIR="${SCRIPT_DIR}/logs"
PIDFILE="${LOGDIR}/adapt.pid"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
LOGFILE="${LOGDIR}/adapt_${TIMESTAMP}.log"

if [ ! -x "${PYTHON}" ]; then
    echo "ERRO: Python do ambiente virtual não encontrado: ${PYTHON}"
    echo "Execute 'make setup' primeiro."
    exit 1
fi

if [ $# -eq 0 ]; then
    echo "Uso: $0 [argumentos para adapt_dataset.py]"
    echo ""
    echo "Exemplos:"
    echo "  $0 --provider ollama --model llama3.2:latest --input train-MGS.csv --resume --workers 2"
    echo "  $0 --provider anthropic --input all --resume --workers 8"
    echo "  $0 --provider groq --input train-MGS.csv --resume --workers 4 --verbose"
    echo ""
    echo "Use --help para ver todas as opções do adapt_dataset.py"
    exit 1
fi

mkdir -p "${LOGDIR}"

echo "============================================"
echo " Iniciando adapt_dataset.py em background"
echo "============================================"
echo " Log stdout: ${LOGFILE}"
echo " Log struct: ${LOGDIR}/adapt_dataset.log"
echo " PID       : será salvo em ${PIDFILE}"
echo " Comando   : ${PYTHON} adapt_dataset.py $*"
echo ""
echo " Monitorar: tail -f ${LOGFILE}"
echo " Parar    : kill \$(cat ${PIDFILE})"
echo ""

# Se já existe um processo rodando, avisa (e aborta se não houver TTY para confirmar)
if [ -f "${PIDFILE}" ] && kill -0 "$(cat "${PIDFILE}")" 2>/dev/null; then
    echo "AVISO: Já existe um processo em execução (PID $(cat "${PIDFILE}"))."
    echo "  Para pará-lo: kill $(cat "${PIDFILE}")"
    echo "  Para forçar  : kill -9 $(cat "${PIDFILE}") && rm ${PIDFILE}"
    echo ""
    if [ -t 0 ]; then
        read -r -p "Deseja iniciar mesmo assim? [s/N] " resposta
        if [[ ! "${resposta}" =~ ^[Ss]$ ]]; then
            exit 0
        fi
    else
        echo "Entrada não interativa — abortando para evitar execução dupla."
        exit 1
    fi
fi

# Executa em background com nohup
nohup "${PYTHON}" "${SCRIPT_DIR}/adapt_dataset.py" "$@" >> "${LOGFILE}" 2>&1 &
PID=$!

echo "${PID}" > "${PIDFILE}"

echo "Processo iniciado com PID ${PID}"
echo ""
echo "Para monitorar o progresso:"
echo "  # stdout/stderr do nohup (resumo da execução)"
echo "  tail -f ${LOGFILE}"
echo ""
echo "  # logs estruturados do Python (nível DEBUG, inclui respostas brutas)"
echo "  tail -f ${LOGDIR}/adapt_dataset.log"
echo ""
echo "Para parar graciosamente (SIGTERM → salva checkpoint):"
echo "  kill ${PID}"
echo ""
echo "Para parar imediatamente (SIGKILL → pode perder checkpoint):"
echo "  kill -9 ${PID} && rm ${PIDFILE}"
