#!/usr/bin/env python3
"""
Valida os arquivos CSV adaptados pelo adapt_dataset.py.

Uso:
    .venv/bin/python validate_adapted.py dataset/train-MGS-BR.csv
    .venv/bin/python validate_adapted.py --all
    .venv/bin/python validate_adapted.py --all --strict --json relatorio.json

A implementação vive em mgsbr/validate.py (este arquivo é só o ponto de entrada).
"""

import sys

from mgsbr.validate import main

if __name__ == "__main__":
    sys.exit(main())
