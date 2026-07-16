# MGS-BR Dataset — Agent Guide

## Entry points

- `adapt_dataset.py` and `validate_adapted.py` are thin wrappers; real logic lives in `mgsbr/` package.
- `mgsbr/cli.py` is the orchestrator; `mgsbr/adapter.py` is the core pipeline.
- `mgsbr/runtime.py` owns logging setup (`setup_logging()`) and signal handlers (`install_signal_handlers()`). The global `shutdown_requested` threading.Event is checked by workers between requests.

## Dev commands (use Makefile, not raw python)

| Command | What |
|---|---|
| `make setup-dev` | venv + all deps (incl. pytest, ruff) |
| `make test` | `python -m pytest` (no network — fake LLM in conftest.py) |
| `make lint` | `ruff check mgsbr tests adapt_dataset.py validate_adapted.py` |
| `make sample` | 20-line test via Ollama (requires `ollama pull qwen2.5:7b`) |
| `make validate-all` | validate all `dataset/*-MGS-BR.csv` (exit 1 on errors) |
| `make datacard` | regenerate `dataset/README.md` from CSVs |
| `make status` | show background PID + checkpoint line counts |
| `make clean` | removes outputs but **preserves** checkpoints (API cost) |
| `make clean-all` | removes outputs **and** checkpoints |

## Ruff config (pyproject.toml)

- line-length=110, target py310, select E4/E7/E9/F/I/B/UP

## Test quirks

- `conftest.py` provides `EchoLLM` (echoes IDs) and `ScriptedLLM` (predefined responses + exceptions). Use these instead of real LLM calls.
- `@pytest.fixture(autouse=True)` sets `RETRY_DELAY=0` and clears `shutdown_requested` flag.

## Pipeline quirks

- **Checkpoints**: `.checkpoints/<stem>_checkpoint.jsonl`. Only lines answered by API are saved. Use `--resume` to skip done lines; `--retry-failed` to also reprocess empty-translation lines.
- **Without `--resume`**, old checkpoint is archived to `*.bak-<timestamp>` (prevents cross-model contamination).
- **`--input all`** processes train + test in parallel; each file gets its own adapter instance.
- **`--verbose`** shows raw LLM responses (debug mode).
- **`--workers N`** (default 4) controls `ThreadPoolExecutor` parallelism.
- **`--batch-size N`** (default 5) — smaller batches reduce JSON truncation in small models.
- **`--sample N`** processes only N lines (fast iteration without full dataset).
- **`--no-parquet`** skips parquet export (saves time when only CSV is needed).
- **`PROMPT_VERSION`** (`mgsbr/prompts.py:103-105`): `sha256(SYSTEM_PROMPT + BATCH_PROMPT_TEMPLATE)[:12]` recorded in `.run.json` manifests for provenance. If you modify prompts, the hash changes — important for reproducibility.

## Output files

- `dataset/<stem>-MGS-BR.csv` — adapted dataset (train, test, or sample)
- `dataset/<stem>-MGS-BR.parquet` — same data in parquet (skip with `--no-parquet`)
- `dataset/<stem>-MGS-BR.run.json` — provenance manifest (provider, model, prompt hash, params, metrics, tokens)
- `dataset/adaptation-decisions-<stem>.md` — per-file decision log grouped by class
- `.checkpoints/<stem>_checkpoint.jsonl` — incremental checkpoint for resume

## LLM provider notes

- Anthropic uses `anthropic` SDK; all others use `openai` SDK with custom `base_url`. Lazy import — only one SDK needs to be installed.
- Local providers (Ollama, LM Studio) use `api_key="no-key-required"`.
- `.env` loaded automatically via `python-dotenv` at startup.

## JSON parsing gotchas

- `_strip_markdown_fences()` handles nested ``` fences (common in local models).
- `_normalize_parsed_json()` wraps single objects in array, filters non-dict items, rejects null/str/int.
- `_TYPE_NORM` dict converts PT-BR keys (`raça`→`race`, `gênero`→`gender`, etc.) — small models often ignore the EN-key instruction.
- All field access uses `obj.get("field") or default` pattern (not `.get(key, default)`) because models return `null`.
- `_safe_float()` handles None, empty strings, non-numeric strings → `0.0`.
- `json-repair` library recovers malformed JSON (extra commas, translated keys, broken escaping).

## Validation quirks

- `validate_adapted.py --all --strict` turns warnings into exit 1.
- `validate_adapted.py --all --json relatorio.json` for CI-friendly output.
- Checks: column presence, row count vs original, marker preservation, `decision_id` uniqueness, `legal_status_br` without specific law, `unrelated` labeled as crime, empty translations.

## Legal classification (hard-won context)

- `crime_racismo`: Lei 7.716/1989 + Lei 14.532/2023 Art. 2-A (race/color/ethnicity/provenance). **Religion is NOT in Art. 2-A** — stays under CP Art. 140 §3º (prescriptible).
- `orientacao_sexual` category: STF ADO 26/2019 (homophobia/transphobia = racism).
- `regiao` category: no specific federal criminal law — use `vies_cultural`.
- `crime_trabalho`: Lei 9.029/1995 (includes "situação familiar" per Lei 13.146/2015).
- `neutro`: fallback for out-of-schema values (e.g. `"unrelated"`).

## Background execution

- `./run_background.sh` uses nohup, saves PID to `logs/adapt.pid`.
- `make status` checks if process is alive and shows checkpoint progress.
- Signal handlers (SIGTERM/SIGINT) save checkpoint before exit.
