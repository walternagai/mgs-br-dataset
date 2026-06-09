#!/usr/bin/env bash
#
# Executa o script adapt_dataset.py em background com logging adequado.
#
# Uso:
#   ./run_background.sh [argumentos para adapt_dataset.py]
#
# Exemplos:
#   ./run_background.sh --provider ollama --model llama3.2:latest --input train-MGS.csv --resume
#   ./run_background.sh --provider anthropic --input all --resume
#
# O script:
#   - Cria diretório logs/ se necessário
#   - Gera arquivo de log com timestamp
#   - Salva o PID em logs/adapt.pid
#   - Executa com nohup em background
#   - Mostra comandos para monitorar e parar o processo

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
    echo "  $0 --provider ollama --model llama3.2:latest --input train-MGS.csv --resume"
    echo "  $0 --provider anthropic --input all --resume"
    echo ""
    echo "Use --help para ver todas as opções do adapt_dataset.py"
    exit 1
fi

mkdir -p "${LOGDIR}"

echo "============================================"
echo " Iniciando adapt_dataset.py em background"
echo "============================================"
echo " Log      : ${LOGFILE}"
echo " PID      : será salvo em ${PIDFILE}"
echo " Comando  : ${PYTHON} adapt_dataset.py $*"
echo ""
echo " Monitorar: tail -f ${LOGFILE}"
echo " Parar    : kill \$(cat ${PIDFILE})"
echo ""

# Se já existe um processo rodando, avisa
if [ -f "${PIDFILE}" ] && kill -0 "$(cat "${PIDFILE}")" 2>/dev/null; then
    echo "AVISO: Já existe um processo em execução (PID $(cat "${PIDFILE}"))."
    echo "  Para pará-lo: kill $(cat "${PIDFILE}")"
    echo "  Para forçar  : kill -9 $(cat "${PIDFILE}") && rm ${PIDFILE}"
    echo ""
    read -r -p "Deseja iniciar mesmo assim? [s/N] " resposta
    if [[ ! "${resposta}" =~ ^[Ss]$ ]]; then
        exit 0
    fi
fi

# Executa em background com nohup
nohup "${PYTHON}" "${SCRIPT_DIR}/adapt_dataset.py" "$@" >> "${LOGFILE}" 2>&1 &
PID=$!

echo "${PID}" > "${PIDFILE}"

echo "Processo iniciado com PID ${PID}"
echo ""
echo "Para monitorar o progresso:"
echo "  tail -f ${LOGFILE}"
echo ""
echo "Para parar graciosamente (salva checkpoint):"
echo "  kill ${PID}"
echo ""
echo "Para parar imediatamente (pode perder checkpoint):"
echo "  kill -9 ${PID} && rm ${PIDFILE}"
