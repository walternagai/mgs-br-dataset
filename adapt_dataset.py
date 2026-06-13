#!/usr/bin/env python3
"""
Adapta o dataset MGS (Multi-Grain Stereotypes) para o contexto jurídico-cultural brasileiro,
traduzindo textos EN→PT-BR e acrescentando colunas de classificação legal.

Saída: dataset/<stem>-MGS-BR.csv (+ .parquet e .run.json)  +  dataset/adaptation-decisions-<stem>.md

Uso: .venv/bin/python adapt_dataset.py --help

A implementação vive no pacote mgsbr/ (este arquivo é só o ponto de entrada).
"""

import sys

from mgsbr.cli import main

if __name__ == "__main__":
    sys.exit(main())
