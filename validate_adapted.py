#!/usr/bin/env python3
"""
Valida os arquivos CSV adaptados pelo adapt_dataset.py.

Verifica:
  1. Integridade das colunas novas
  2. Distribuição por categoria antes/depois
  3. Cobertura das novas categorias (regiao, orientacao_sexual)
  4. Linhas com confianca_traducao_br < 0.5 (requerem revisão humana)
  5. Consistência entre stereotype_type_br e legal_status_br

Uso:
    .venv/bin/python validate_adapted.py dataset/train-MGS-BR.csv
    .venv/bin/python validate_adapted.py dataset/test-MGS-BR.csv
"""

import sys
import pandas as pd
from pathlib import Path
from collections import Counter

REQUIRED_NEW_COLS = [
    "text_with_marker_br",
    "text_no_marker_br",
    "stereotype_type_br",
    "legal_status_br",
    "lei_referencia_br",
    "confianca_traducao_br",
    "decision_id",
]

VALID_STEREOTYPE_TYPES_BR = {
    "race", "gender", "profession", "religion", "regiao", "orientacao_sexual"
}

VALID_LEGAL_STATUS = {"crime_racismo", "crime_trabalho", "vies_cultural", "neutro"}


def validate(filepath: str):
    path = Path(filepath)
    if not path.exists():
        print(f"Arquivo não encontrado: {path}")
        sys.exit(1)

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    total = len(df)
    print(f"\n{'='*60}")
    print(f"Validando: {path.name}  ({total} linhas)")
    print(f"{'='*60}")

    # 1. Colunas novas presentes
    missing = [c for c in REQUIRED_NEW_COLS if c not in df.columns]
    if missing:
        print(f"[ERRO] Colunas ausentes: {missing}")
    else:
        print("[OK] Todas as colunas novas presentes")

    if "confianca_traducao_br" in df.columns:
        df["confianca_traducao_br"] = pd.to_numeric(df["confianca_traducao_br"], errors="coerce").fillna(0.0)

    # 2. Distribuição stereotype_type (original vs BR)
    print("\n--- Distribuição stereotype_type (original) ---")
    if "stereotype_type" in df.columns:
        for k, v in Counter(df["stereotype_type"]).most_common():
            print(f"  {k:<25} {v:>6}  ({v/total*100:.1f}%)")

    print("\n--- Distribuição stereotype_type_br (adaptado) ---")
    if "stereotype_type_br" in df.columns:
        for k, v in Counter(df["stereotype_type_br"]).most_common():
            flag = " ★ NOVA" if k in ("regiao", "orientacao_sexual") else ""
            invalid = " [INVÁLIDO]" if k not in VALID_STEREOTYPE_TYPES_BR else ""
            print(f"  {k:<25} {v:>6}  ({v/total*100:.1f}%){flag}{invalid}")

    # 3. Cobertura de novas categorias
    print("\n--- Cobertura de novas categorias ---")
    if "stereotype_type_br" in df.columns:
        for cat in ("regiao", "orientacao_sexual"):
            n = (df["stereotype_type_br"] == cat).sum()
            print(f"  {cat}: {n} linhas ({n/total*100:.2f}%)")

    # 4. legal_status_br
    print("\n--- Distribuição legal_status_br ---")
    if "legal_status_br" in df.columns:
        for k, v in Counter(df["legal_status_br"]).most_common():
            invalid = " [INVÁLIDO]" if k not in VALID_LEGAL_STATUS else ""
            print(f"  {k:<20} {v:>6}  ({v/total*100:.1f}%){invalid}")

    # 5. Confiança
    if "confianca_traducao_br" in df.columns:
        conf = df["confianca_traducao_br"]
        print(f"\n--- Distribuição confiança (media={conf.mean():.3f}, min={conf.min():.2f}, max={conf.max():.2f}) ---")
        alta = (conf >= 0.9).sum()
        mod_alta = ((conf >= 0.7) & (conf < 0.9)).sum()
        mod = ((conf >= 0.5) & (conf < 0.7)).sum()
        baixa = (conf < 0.5).sum()
        print(f"  Alta    (≥0.9):   {alta:>6}  ({alta/total*100:.1f}%)")
        print(f"  Mod-alta(0.7-0.89):{mod_alta:>5}  ({mod_alta/total*100:.1f}%)")
        print(f"  Moderada(0.5-0.69):{mod:>5}  ({mod/total*100:.1f}%)")
        print(f"  Baixa   (<0.5):   {baixa:>6}  ({baixa/total*100:.1f}%)  ← revisar manualmente")

    # 6. Consistência race → deve ter legal_status crime_racismo ou crime_trabalho
    if "stereotype_type_br" in df.columns and "legal_status_br" in df.columns:
        race_mask = df["stereotype_type_br"] == "race"
        race_neutral = (race_mask & (df["legal_status_br"] == "neutro")).sum()
        if race_neutral > 0:
            print(f"\n[ATENÇÃO] {race_neutral} linhas de tipo 'race' com legal_status='neutro' — verifique")

        # linhas race sem lei_referencia_br
        if "lei_referencia_br" in df.columns:
            race_sem_lei = (race_mask & (df["lei_referencia_br"].isin(["", "neutro"]))).sum()
            if race_sem_lei > 0:
                print(f"[ATENÇÃO] {race_sem_lei} linhas de tipo 'race' sem referência legal — verifique")

    # 7. Tradução vazia
    if "text_no_marker_br" in df.columns:
        vazias = (df["text_no_marker_br"] == "").sum()
        if vazias:
            print(f"\n[ATENÇÃO] {vazias} linhas sem tradução (text_no_marker_br vazio) — reprocessar")

    print("\n[Validação concluída]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: .venv/bin/python validate_adapted.py <arquivo-BR.csv>")
        sys.exit(1)
    validate(sys.argv[1])
