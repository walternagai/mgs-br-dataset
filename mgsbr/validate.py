"""Validação dos CSVs adaptados pelo adapt_dataset.py.

Verifica:
  1. Integridade das colunas novas e contagem de linhas vs. original
  2. Distribuição por categoria antes/depois
  3. Cobertura das novas categorias (regiao, orientacao_sexual)
  4. Preservação dos ===marcadores=== nas traduções
  5. Unicidade de decision_id
  6. Consistência entre stereotype_type_br, legal_status_br, lei_referencia_br e label
  7. Linhas com confianca_traducao_br < 0.5 ou sem tradução (revisão humana)

Exit code 1 quando há erros (ou atenções, com --strict) — utilizável em CI/Make.
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

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
CRIME_STATUSES = {"crime_racismo", "crime_trabalho"}

# Referência legal minimamente específica: cita lei numerada, CF, CP, STF ou ADO.
LEI_REF_REGEX = r"(?i)(?:lei\s*n?º?\s*\d|cf\s*/?\s*\d|constitui|cp\s+art|art\.?\s*\d+|stf|ado\s*26)"


def find_original(path: Path) -> Path | None:
    """Infere o CSV original a partir do adaptado: train-MGS-BR.csv → train-MGS.csv."""
    candidate = path.with_name(path.name.replace("-MGS-BR", "-MGS"))
    return candidate if candidate != path and candidate.exists() else None


def marker_pairs(text: str) -> int:
    return str(text).count("===") // 2


def validate_file(path: Path) -> dict:
    report = {"file": str(path), "errors": [], "warnings": [], "stats": {}}

    def err(msg: str):
        report["errors"].append(msg)
        print(f"[ERRO] {msg}")

    def warn(msg: str):
        report["warnings"].append(msg)
        print(f"[ATENÇÃO] {msg}")

    if not path.exists():
        print(f"\n{'='*60}\nValidando: {path}\n{'='*60}")
        err(f"Arquivo não encontrado: {path}")
        return report

    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    total = len(df)
    report["stats"]["rows"] = total
    print(f"\n{'='*60}")
    print(f"Validando: {path.name}  ({total} linhas)")
    print(f"{'='*60}")

    if total == 0:
        err("Arquivo vazio")
        return report

    # 1a. Colunas novas presentes
    missing = [c for c in REQUIRED_NEW_COLS if c not in df.columns]
    if missing:
        err(f"Colunas ausentes: {missing}")
    else:
        print("[OK] Todas as colunas novas presentes")

    # 1b. Contagem de linhas vs. original
    original = find_original(path)
    if original is not None:
        orig_total = len(pd.read_csv(original, usecols=[0]))
        report["stats"]["original_rows"] = orig_total
        if orig_total != total:
            warn(
                f"Linhas: {total} no adaptado vs {orig_total} no original "
                f"({original.name}) — diferença esperada apenas com --sample"
            )
        else:
            print(f"[OK] Contagem de linhas igual ao original ({original.name})")

    # 5. decision_id presente e único
    if "decision_id" in df.columns:
        empty_ids = int((df["decision_id"] == "").sum())
        if empty_ids:
            err(f"{empty_ids} linhas com decision_id vazio")
        nonempty = df.loc[df["decision_id"] != "", "decision_id"]
        dups = int(len(nonempty) - nonempty.nunique())
        if dups:
            err(f"{dups} decision_id duplicados")
        elif not empty_ids:
            print("[OK] decision_id presente e único em todas as linhas")

    if "confianca_traducao_br" in df.columns:
        conf = pd.to_numeric(df["confianca_traducao_br"], errors="coerce")
        n_invalid_conf = int(conf.isna().sum())
        if n_invalid_conf:
            err(f"{n_invalid_conf} linhas com confianca_traducao_br não numérica")
        df["confianca_traducao_br"] = conf.fillna(0.0)

    # 2. Distribuição stereotype_type (original vs BR)
    print("\n--- Distribuição stereotype_type (original) ---")
    if "stereotype_type" in df.columns:
        for k, v in Counter(df["stereotype_type"]).most_common():
            print(f"  {k:<25} {v:>6}  ({v/total*100:.1f}%)")

    print("\n--- Distribuição stereotype_type_br (adaptado) ---")
    if "stereotype_type_br" in df.columns:
        invalid_types = set()
        for k, v in Counter(df["stereotype_type_br"]).most_common():
            flag = " ★ NOVA" if k in ("regiao", "orientacao_sexual") else ""
            invalid = ""
            if k not in VALID_STEREOTYPE_TYPES_BR:
                invalid = " [INVÁLIDO]"
                invalid_types.add(k)
            print(f"  {k:<25} {v:>6}  ({v/total*100:.1f}%){flag}{invalid}")
        if invalid_types:
            err(f"Valores de stereotype_type_br fora do schema: {sorted(invalid_types)}")

    # 3. Cobertura de novas categorias
    print("\n--- Cobertura de novas categorias ---")
    if "stereotype_type_br" in df.columns:
        for cat in ("regiao", "orientacao_sexual"):
            n = int((df["stereotype_type_br"] == cat).sum())
            report["stats"][f"cobertura_{cat}"] = n
            print(f"  {cat}: {n} linhas ({n/total*100:.2f}%)")

    # 6a. legal_status_br dentro do schema
    print("\n--- Distribuição legal_status_br ---")
    if "legal_status_br" in df.columns:
        invalid_legal = set()
        for k, v in Counter(df["legal_status_br"]).most_common():
            invalid = ""
            if k not in VALID_LEGAL_STATUS:
                invalid = " [INVÁLIDO]"
                invalid_legal.add(k)
            print(f"  {k:<20} {v:>6}  ({v/total*100:.1f}%){invalid}")
        if invalid_legal:
            err(f"Valores de legal_status_br fora do schema: {sorted(invalid_legal)}")

    # 7a. Confiança
    if "confianca_traducao_br" in df.columns:
        conf = df["confianca_traducao_br"]
        print(
            f"\n--- Distribuição confiança "
            f"(media={conf.mean():.3f}, min={conf.min():.2f}, max={conf.max():.2f}) ---"
        )
        alta     = int((conf >= 0.9).sum())
        mod_alta = int(((conf >= 0.7) & (conf < 0.9)).sum())
        mod      = int(((conf >= 0.5) & (conf < 0.7)).sum())
        baixa    = int((conf < 0.5).sum())
        report["stats"]["confidence"] = {
            "alta": alta, "moderada_alta": mod_alta, "moderada": mod, "baixa": baixa,
            "media": round(float(conf.mean()), 4),
        }
        print(f"  Alta    (≥0.9):   {alta:>6}  ({alta/total*100:.1f}%)")
        print(f"  Mod-alta(0.7-0.89):{mod_alta:>5}  ({mod_alta/total*100:.1f}%)")
        print(f"  Moderada(0.5-0.69):{mod:>5}  ({mod/total*100:.1f}%)")
        print(f"  Baixa   (<0.5):   {baixa:>6}  ({baixa/total*100:.1f}%)  ← revisar manualmente")

    # 6b. Consistência race ↔ legal_status / lei_referencia
    if "stereotype_type_br" in df.columns and "legal_status_br" in df.columns:
        print()
        race_mask = df["stereotype_type_br"] == "race"
        race_neutral = int((race_mask & (df["legal_status_br"] == "neutro")).sum())
        if race_neutral > 0:
            warn(f"{race_neutral} linhas de tipo 'race' com legal_status='neutro' — verifique")

        if "lei_referencia_br" in df.columns:
            race_sem_lei = int(
                (race_mask & (df["lei_referencia_br"].isin(["", "neutro"]))).sum()
            )
            if race_sem_lei > 0:
                warn(f"{race_sem_lei} linhas de tipo 'race' sem referência legal — verifique")

    # 6c. Status criminal exige referência legal específica
    if {"legal_status_br", "lei_referencia_br"} <= set(df.columns):
        crime_mask = df["legal_status_br"].isin(CRIME_STATUSES)
        bad_ref = int(
            (crime_mask & ~df["lei_referencia_br"].str.contains(LEI_REF_REGEX, regex=True)).sum()
        )
        if bad_ref:
            warn(
                f"{bad_ref} linhas com status criminal mas lei_referencia_br "
                f"vazia/inespecífica (ex.: 'Lei' truncada)"
            )

        # 6d. Coerência com o label original
        if "label" in df.columns:
            incoerentes = int(((df["label"] == "unrelated") & crime_mask).sum())
            if incoerentes:
                warn(f"{incoerentes} linhas 'unrelated' classificadas como crime — verifique")

    # 4. Preservação dos marcadores
    if {"text_with_marker", "text_with_marker_br"} <= set(df.columns):
        translated = df["text_with_marker_br"] != ""
        if translated.any():
            orig_marks = df["text_with_marker"].map(marker_pairs)
            br_marks   = df["text_with_marker_br"].map(marker_pairs)
            mismatch   = int((translated & (orig_marks != br_marks)).sum())
            report["stats"]["marker_mismatch"] = mismatch
            if mismatch:
                warn(f"{mismatch} linhas traduzidas não preservam os ===marcadores=== do original")
            else:
                print("[OK] Marcadores ===…=== preservados em todas as traduções")

    # 7b. Tradução vazia
    if "text_no_marker_br" in df.columns:
        vazias = int((df["text_no_marker_br"] == "").sum())
        report["stats"]["sem_traducao"] = vazias
        if vazias:
            warn(f"{vazias} linhas sem tradução (text_no_marker_br vazio) — use --retry-failed")

    return report


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Valida os CSVs adaptados gerados pelo adapt_dataset.py",
    )
    p.add_argument("files", nargs="*", help="CSV(s) adaptados a validar")
    p.add_argument(
        "--all", action="store_true",
        help="Valida todos os *-MGS-BR.csv encontrados em --dataset-dir",
    )
    p.add_argument("--dataset-dir", default="dataset", metavar="DIR")
    p.add_argument(
        "--strict", action="store_true",
        help="Atenções também resultam em exit code 1",
    )
    p.add_argument(
        "--json", metavar="ARQUIVO", default=None,
        help="Grava o relatório consolidado em JSON",
    )
    args = p.parse_args(argv)

    files = [Path(f) for f in args.files]
    if args.all:
        files += sorted(Path(args.dataset_dir).glob("*-MGS-BR.csv"))
    if not files:
        p.error("informe arquivo(s) a validar ou use --all")

    # remove duplicatas preservando a ordem
    reports = [validate_file(f) for f in dict.fromkeys(files)]

    if args.json:
        Path(args.json).write_text(
            json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nRelatório JSON salvo em: {args.json}")

    n_err  = sum(len(r["errors"]) for r in reports)
    n_warn = sum(len(r["warnings"]) for r in reports)
    print(
        f"\n[Validação concluída] arquivos={len(reports)} "
        f"erros={n_err} atenções={n_warn}"
    )
    if n_err or (args.strict and n_warn):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
