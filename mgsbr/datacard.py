"""Gera o datacard (dataset/README.md) a partir dos CSVs adaptados e manifestos .run.json.

Uso: .venv/bin/python -m mgsbr.datacard [--dataset-dir dataset] [--output dataset/README.md]
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

import pandas as pd

from .prompts import LEGAL_TABLE_MD

SCHEMA_MD = [
    "| Coluna | Tipo | Descrição |",
    "|---|---|---|",
    "| `text_with_marker` | str | Texto original (EN) com `===palavra===` marcada |",
    "| `text_no_marker` | str | Texto original (EN) sem marcadores |",
    "| `label` | str | `stereotype` \\| `anti-stereotype` \\| `unrelated` |",
    "| `stereotype_type` | str | Categoria original (EN) |",
    "| `binary_class` / `multi_class` | str | Classes do dataset MGS original |",
    "| `original_dataset` | str | Fonte (StereoSet, CrowS-Pairs) |",
    "| `text_with_marker_br` | str | Tradução PT-BR preservando `===marcadores===` |",
    "| `text_no_marker_br` | str | Tradução PT-BR sem marcadores |",
    "| `stereotype_type_br` | str | Categoria adaptada (inclui `regiao`, `orientacao_sexual`) |",
    "| `legal_status_br` | str | `crime_racismo` \\| `crime_trabalho` \\| `vies_cultural` \\| `neutro` |",
    "| `lei_referencia_br` | str | Lei específica aplicável (ex.: `Lei 7.716/1989 Art. 20`) |",
    "| `confianca_traducao_br` | float 0–1 | Score de confiabilidade da adaptação |",
    "| `decision_id` | str | ID rastreável no log de decisões |",
]


def _distribution_md(series: pd.Series, total: int) -> list[str]:
    lines = ["| Valor | Linhas | % |", "|---|---|---|"]
    for value, count in Counter(series).most_common():
        label = value if value != "" else "_(vazio)_"
        lines.append(f"| `{label}` | {count} | {count/total*100:.1f}% |")
    return lines


def _file_section(csv_path: Path) -> list[str]:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    total = len(df)
    lines = [f"## `{csv_path.name}`", "", f"- **Linhas:** {total}"]

    manifest_path = csv_path.with_name(csv_path.stem + ".run.json")
    if manifest_path.exists():
        try:
            m = json.loads(manifest_path.read_text(encoding="utf-8"))
            lines += [
                f"- **Provedor/modelo:** `{m.get('provider')}` / `{m.get('model')}`",
                f"- **Versão do prompt:** `{m.get('prompt_version')}`",
                f"- **Gerado em:** {m.get('finished_at')}",
                f"- **Proveniência completa:** [`{manifest_path.name}`]({manifest_path.name})",
            ]
        except (json.JSONDecodeError, OSError):
            pass

    if "confianca_traducao_br" in df.columns and total:
        conf = pd.to_numeric(df["confianca_traducao_br"], errors="coerce").fillna(0.0)
        sem_traducao = (
            int((df["text_no_marker_br"] == "").sum())
            if "text_no_marker_br" in df.columns else 0
        )
        lines += [
            f"- **Confiança média:** {conf.mean():.3f}"
            f" (baixa <0.5: {int((conf < 0.5).sum())} linhas)",
        ]
        if sem_traducao:
            lines.append(f"- **Sem tradução (pendentes):** {sem_traducao} linhas")

    if "stereotype_type_br" in df.columns and total:
        lines += ["", "### Distribuição `stereotype_type_br`", ""]
        lines += _distribution_md(df["stereotype_type_br"], total)
    if "legal_status_br" in df.columns and total:
        lines += ["", "### Distribuição `legal_status_br`", ""]
        lines += _distribution_md(df["legal_status_br"], total)

    lines.append("")
    return lines


def build_datacard(dataset_dir: Path) -> str | None:
    files = sorted(dataset_dir.glob("*-MGS-BR.csv"))
    if not files:
        return None

    lines = [
        "# MGS-BR — Datacard",
        "",
        "Adaptação do dataset **MGS (Multi-Grain Stereotypes)** para o contexto",
        "jurídico-cultural brasileiro: tradução EN→PT-BR e classificação conforme a",
        "legislação antidiscriminatória vigente. Gerado automaticamente por",
        "`python -m mgsbr.datacard` — não edite manualmente.",
        "",
        f"_Atualizado em: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
        "## Schema",
        "",
        *SCHEMA_MD,
        "",
    ]
    for f in files:
        lines += _file_section(f)

    lines += [
        "## Marco Legal Consultado",
        "",
        *LEGAL_TABLE_MD,
        "",
        "## Logs de decisão",
        "",
        "Cada arquivo possui um log `adaptation-decisions-<stem>.md` com as decisões",
        "de adaptação agrupadas por classe (substituição de grupo, nova categoria,",
        "reclassificação jurídica, adaptação geográfica, manutenção, descarte).",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Gera o datacard do dataset adaptado")
    p.add_argument("--dataset-dir", default="dataset", metavar="DIR")
    p.add_argument("--output", default=None, metavar="ARQUIVO",
                   help="Destino (default: <dataset-dir>/README.md)")
    args = p.parse_args(argv)

    dataset_dir = Path(args.dataset_dir)
    content = build_datacard(dataset_dir)
    if content is None:
        print(f"Nenhum *-MGS-BR.csv encontrado em {dataset_dir}/ — nada a fazer.")
        return 1

    output = Path(args.output) if args.output else dataset_dir / "README.md"
    output.write_text(content, encoding="utf-8")
    print(f"Datacard salvo em: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
