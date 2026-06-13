# Changelog

Todas as mudanças notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado no [Keep a Changelog](https://keepachangelog.com/),
e o versionamento segue o [Semantic Versioning](https://semver.org/lang/pt-BR/).

---

## [0.7.0] — 2026-06-12

### Fixed

- **Lotes falhos não são mais marcados como processados**: apenas linhas efetivamente respondidas pela API entram no checkpoint; linhas de lotes que esgotaram os retries permanecem pendentes e são reprocessadas com `--resume`.
- **Checkpoint antigo não contamina mais execuções sem `--resume`**: o checkpoint existente é arquivado em `*.bak-<timestamp>` antes de uma execução nova.
- **IDs retornados pelo LLM agora são validados contra o lote**: respostas parciais ou com IDs trocados disparam retry apenas das linhas faltantes; objetos com IDs desconhecidos são descartados com log.
- Métricas e log de decisões não se misturam mais entre train e test no modo `--input all` (adapter novo por arquivo).

### Added

- Flag `--retry-failed`: como `--resume`, mas reprocessa também linhas que ficaram sem tradução em execuções anteriores.
- Tratamento dedicado de rate limit e erros transitórios (429/5xx/timeout) no `LLMClient`: backoff exponencial + jitter, até 8 tentativas, respeito ao header `retry-after` — separado do retry de parsing JSON.
- Manifesto de proveniência `dataset/<stem>-MGS-BR.run.json` por execução: provedor, modelo, hash da versão do prompt (`PROMPT_VERSION`), parâmetros, métricas e tokens consumidos.
- Contagem de tokens (entrada/saída/requisições) por arquivo, exibida no resumo e gravada no manifesto.
- Exportação automática para parquet (`dataset/<stem>-MGS-BR.parquet`, desativável com `--no-parquet`); `pyarrow` adicionado às dependências.
- `validate_adapted.py` reescrito: exit code 1 em erros (utilizável em CI), `--all`, `--strict`, relatório `--json`, e novas verificações — preservação dos `===marcadores===`, unicidade de `decision_id`, contagem de linhas vs. original, referência legal inespecífica em status criminal, e coerência `label` × `legal_status_br`.
- Datacard gerado por `python -m mgsbr.datacard` (ou `make datacard`) em `dataset/README.md`.
- Suíte de testes com pytest (40 testes, LLM falso, sem rede) cobrindo parsing, retry por IDs, checkpoint, resume/retry-failed e validação; configuração de `ruff` em `pyproject.toml`; `requirements-dev.txt` e alvos `make setup-dev`, `make test`, `make lint`.
- Novos alvos no Makefile: `validate-all`, `retry-failed`, `datacard`, `status`, `clean-all` — `make clean` agora **preserva** os checkpoints (que representam horas de API paga).
- Métrica `batches_partial` e contagem de linhas sem resposta (`rows_failed`).

### Changed

- **Código modularizado no pacote `mgsbr/`** (`providers`, `prompts`, `parsing`, `checkpoint`, `adapter`, `validate`, `datacard`, `cli`, `runtime`); `adapt_dataset.py` e `validate_adapted.py` viram pontos de entrada finos, mantendo os comandos documentados.
- Log de decisões agora é por arquivo: `dataset/adaptation-decisions-<stem>.md` (antes um único `adaptation-decisions.md` sobrescrito a cada execução).
- Loop de progresso usa `concurrent.futures.as_completed` em vez de polling com `time.sleep`.
- `run_background.sh` aborta em vez de travar no prompt de confirmação quando não há TTY.
- Esperas de retry interruptíveis pelo shutdown gracioso (`threading.Event.wait` em vez de `time.sleep`).

## [0.6.1] — 2026-06-09

### Added

- Validação estrutural da resposta JSON do LLM via `_normalize_parsed_json()`, que garante que `adapt_batch()` sempre retorne `list[dict]`, tratando objetos únicos, valores nulos, strings, números e listas mistas.
- Tratamento de campos `None` (`null` no JSON) em `merge_results()`: todos os acessos via `.get()` usam o padrão `or default`, eliminando `AttributeError: 'NoneType' object has no attribute 'lower'`.
- Helper `_safe_float()` para conversão robusta de `confianca_traducao_br`, tolerando `None`, strings não numéricas e strings vazias.
- Retornos vazios do LLM agora levantam `RuntimeError` em `LLMClient.complete()` em vez de propagarem `NoneType`, permitindo captura e retry.
- Métricas de processamento de batch: `batches_ok`, `batches_repaired`, `batches_fail` exibidas ao final de cada arquivo.
- Log da resposta bruta do LLM (primeiros 500 caracteres) no arquivo de log em caso de falha de parsing após todos os retries.
- Melhoria em `_strip_markdown_fences()`: loop `while` remove múltiplos níveis de ` ``` ` aninhados, comum em modelos locais como `gemma4`.
- Flag `--verbose` para exibir logs de nível DEBUG no console (incluindo respostas brutas e tentativas de retry).

## [0.6.0] — 2026-06-09

### Added

- Processamento paralelo de batches via `ThreadPoolExecutor`, com workers configuráveis (`--workers N`, default 4).
- Integração com `json-repair` para recuperação automática de JSON malformado (vírgulas extras, chaves traduzidas, escaping quebrado).
- Suporte a arquivo `.env` via `python-dotenv` — `load_dotenv()` é chamado automaticamente no início do script.
- Template `.env.example` com as variáveis `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GROQ_API_KEY`, `MARITACA_API_KEY`.
- Regex `CRÍTICA — Formato JSON` no system prompt para prevenir tradução de chaves JSON por modelos PT-BR como o Sabia.
- Modelo padrão do provedor Maritaca atualizado para `sabia-4`.
- `--workers` adicionado ao `build_parser()` e a `process_file()`.

### Changed

- `DEFAULT_BATCH_SIZE` reduzido de 10 para 5 para reduzir taxa de JSON truncado em modelos menores.
- `merge_results()` e `save_decision_log()` protegidos por `threading.Lock` para segurança em execução paralela.

### Fixed

- `.gitignore` atualizado para bloquear arquivos `.env`.

## [0.5.0] — 2026-06-08

### Added

- Sistema de logging estruturado com `logging` da stdlib: logs de nível DEBUG para arquivo (`logs/adapt_dataset.log`), WARNING para console.
- Signal handlers (`SIGTERM`, `SIGINT`) para shutdown gracioso com `_shutdown_requested` via `threading.Event`.
- Script `run_background.sh` para execução em background com `nohup` e captura de PID em `logs/adapt.pid`.
- Evento `KeyboardInterrupt` tratado no loop de processamento paralelo.

### Changed

- Console handler configurado com `sys.stdout` para compatibilidade com `tqdm` em modo `disable=not sys.stdout.isatty()`.
- Log de conclusão inclui métricas `alta`, `mod`, `baixa`.

## [0.4.0] — 2026-06-08

### Added

- Função `_TYPE_NORM` para normalização de chaves PT-BR (`raça` → `race`, `gênero` → `gender`, etc.) retornadas por modelos menores como `llama3.2`.
- Função `_strip_markdown_fences()` para remover blocos ` ```json ``` ` inseridos por modelos.
- Retry automático (3 tentativas, backoff linear de 5s) em `adapt_batch()` para falhas de parsing JSON.
- Checkpoints incrementais em `.checkpoints/*.jsonl` com retomada via `--resume`.

### Fixed

- `pandas` fixado na versão 2.2.3 por incompatibilidade com 3.0.x.

## [0.3.0] — 2026-06-07

### Added

- Abstração multi-provedor `LLMClient` com suporte a Anthropic SDK e OpenAI SDK (lazy import).
- Presets de 7 provedores: `anthropic`, `openai`, `groq`, `maritaca`, `ollama`, `lmstudio`, `custom`.
- Coluna `stereotype_type_br` com valores validados contra `_VALID_TYPES`.
- Coluna `legal_status_br` com valores `crime_racismo`, `crime_trabalho`, `vies_cultural`, `neutro`.
- Validação do dataset adaptado via `validate_adapted.py` (colunas, distribuições, consistência, cobertura).
- Log de decisões `adaptation-decisions.md` agrupado por classe de decisão.
- Makefile com alvos `setup`, `sample`, `validate`, `run-train`, `run-test`, `clean`, `help`.
- MIT License.

### Changed

- Refatoração do `DatasetAdapter` com separação `adapt_batch()` / `merge_results()` / `process_file()`.

## [0.2.0] — 2026-06-06

### Added

- Script `adapt_dataset.py` com pipeline completo de tradução e classificação legal.
- System prompt com framework legal brasileiro (CF/88, Lei 7.716/1989, Lei 14.532/2023, STF ADO 26/2019, Lei 9.029/1995).
- Prompt de batch com schema JSON de 9 campos: `text_with_marker_br`, `text_no_marker_br`, `stereotype_type_br`, `legal_status_br`, `lei_referencia_br`, `confianca_traducao_br`, `decision_class`, `decision_justificativa`.
- Cálculo de confiança composto por equivalência linguística (40%), alinhamento jurídico (40%) e transferência cultural (20%).

## [0.1.0] — 2026-06-06

### Added

- Estrutura inicial do repositório: `dataset/`, `.checkpoints/`, `logs/`.
- `requirements.txt` com `anthropic==0.107.1`, `openai==2.41.0`, `pandas==3.0.3`, `tqdm==4.68.1`.
- `.gitignore` para Python, datasets, checkpoints e saídas geradas.
- README.md com documentação do dataset, colunas, valores válidos e exemplos de uso.
