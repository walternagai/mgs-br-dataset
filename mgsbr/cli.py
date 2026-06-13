"""CLI do adapt_dataset: parsing de argumentos e orquestração do pipeline."""

import argparse
from pathlib import Path

from .adapter import DEFAULT_BATCH_SIZE, DEFAULT_WORKERS, DatasetAdapter
from .providers import PROVIDERS, resolve_llm
from .runtime import install_signal_handlers, setup_logging, shutdown_requested

DATASET_DIR = Path("dataset")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Adapta dataset MGS para o contexto jurídico-cultural brasileiro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  # Anthropic (padrão)
  .venv/bin/python adapt_dataset.py --sample 50

  # Ollama local
  .venv/bin/python adapt_dataset.py --provider ollama --model llama3.2 --sample 50

  # LM Studio local
  .venv/bin/python adapt_dataset.py --provider lmstudio --model my-model

  # Groq
  .venv/bin/python adapt_dataset.py --provider groq

  # Maritaca
  .venv/bin/python adapt_dataset.py --provider maritaca

  # Endpoint customizado
  .venv/bin/python adapt_dataset.py --provider custom \\
      --base-url http://meu-servidor/v1 --api-key k --model my-model

  # Processar ambos os arquivos com retomada
  .venv/bin/python adapt_dataset.py --input all --resume

  # Reprocessar apenas as linhas que ficaram sem tradução
  .venv/bin/python adapt_dataset.py --input train-MGS.csv --retry-failed
""",
    )

    p.add_argument(
        "--input", default="train-MGS.csv", metavar="ARQUIVO",
        help="CSV de entrada em dataset/ (default: train-MGS.csv). Use 'all' para ambos.",
    )

    prov = p.add_argument_group("Provedor de LLM")
    prov.add_argument(
        "--provider", default="anthropic",
        choices=list(PROVIDERS.keys()),
        help="Provedor de LLM (default: anthropic)",
    )
    prov.add_argument(
        "--model", default=None, metavar="MODELO",
        help="Nome do modelo (default: depende do provedor)",
    )
    prov.add_argument(
        "--base-url", default=None, metavar="URL",
        help="URL base do endpoint OpenAI-compatible (sobrepõe o preset do provedor)",
    )
    prov.add_argument(
        "--api-key", default=None, metavar="CHAVE",
        help="Chave de API (sobrepõe a variável de ambiente do provedor)",
    )

    proc = p.add_argument_group("Processamento")
    proc.add_argument(
        "--sample", type=int, default=None, metavar="N",
        help="Processar apenas as N primeiras linhas (útil para testes)",
    )
    proc.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE, metavar="N",
        help=f"Linhas por chamada de API (default: {DEFAULT_BATCH_SIZE})",
    )
    proc.add_argument(
        "--resume", action="store_true",
        help="Retoma processamento interrompido a partir do checkpoint",
    )
    proc.add_argument(
        "--retry-failed", action="store_true",
        help="Como --resume, mas também reprocessa linhas que ficaram sem tradução",
    )
    proc.add_argument(
        "--workers", type=int, default=DEFAULT_WORKERS, metavar="N",
        help=f"Requisições paralelas ao LLM (default: {DEFAULT_WORKERS})",
    )
    proc.add_argument(
        "--no-parquet", action="store_true",
        help="Não gera a versão .parquet da saída",
    )
    proc.add_argument(
        "--verbose", action="store_true",
        help="Exibe respostas brutas do LLM no console (modo debug)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    setup_logging(verbose=args.verbose)
    install_signal_handlers()
    shutdown_requested.clear()

    llm = resolve_llm(
        args.provider, model=args.model, base_url=args.base_url, api_key=args.api_key
    )

    input_files = (
        ["train-MGS.csv", "test-MGS.csv"] if args.input == "all" else [args.input]
    )

    for filename in input_files:
        if shutdown_requested.is_set():
            print("Shutdown solicitado — arquivos restantes não processados.")
            break
        input_path = DATASET_DIR / filename
        if not input_path.exists():
            print(f"Arquivo não encontrado: {input_path}")
            continue
        stem        = input_path.stem.replace("-MGS", "")
        output_path = DATASET_DIR / f"{stem}-MGS-BR.csv"

        # Adapter novo por arquivo: métricas e log de decisões não se misturam
        # entre train e test no modo --input all.
        adapter = DatasetAdapter(llm)
        adapter.process_file(
            input_path, output_path,
            sample=args.sample,
            resume=args.resume or args.retry_failed,
            retry_failed=args.retry_failed,
            batch_size=args.batch_size,
            workers=args.workers,
            write_parquet=not args.no_parquet,
        )
        adapter.save_decision_log(DATASET_DIR / f"adaptation-decisions-{stem}.md")

    print("\nConcluído.")
    return 0
