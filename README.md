# MGS-BR — Adaptação do Dataset Multi-Grain Stereotypes para o Contexto Brasileiro

Converte o dataset **MGS** (Multi-Grain Stereotypes) — originalmente em inglês e centrado na realidade americana — para o **contexto jurídico-cultural brasileiro**, traduzindo os textos para PT-BR e acrescentando colunas de classificação legal conforme a legislação vigente.

## Quick Start

```bash
# 1. Clone e configure o ambiente
git clone <repo-url> && cd mgs-br-dataset
make setup

# 2. Configure as chaves de API (escolha uma)
cp .env.example .env   # edite .env com sua(s) chave(s)
# ou exporte diretamente: export ANTHROPIC_API_KEY=sk-ant-...

# 3. Teste o pipeline em 20 linhas (requer Ollama — https://ollama.com)
ollama pull qwen2.5:7b
make sample

# 4. Para processar os datasets completos
.venv/bin/python adapt_dataset.py --input all --resume --workers 4
```

**Sem Ollama?** Qualquer provedor OpenAI-compatible funciona. Veja a seção [Como usar](#como-usar).

```bash
make help   # lista todos os alvos disponíveis
```

## Dataset de entrada

| Arquivo | Linhas | Origem |
|---|---|---|
| `dataset/train-MGS.csv` | 42.201 | StereoSet (intra/inter-sentence) + CrowS-Pairs |
| `dataset/test-MGS.csv` | 10.550 | idem |
| `dataset/sample-MGS.csv` | 20 | Amostra para teste rápido |

**Colunas originais:** `text_with_marker`, `text_no_marker`, `label`, `stereotype_type`, `binary_class`, `multi_class`, `original_dataset`

**Distribuição (treino):** race 46,6% · profession 36,8% · gender 12,5% · religion 4,1%

## Dataset de saída

Os arquivos `dataset/*-MGS-BR.csv` acrescentam sete colunas:

| Coluna | Tipo | Descrição |
|---|---|---|
| `text_with_marker_br` | str | Tradução PT-BR preservando `===marcadores===` |
| `text_no_marker_br` | str | Tradução PT-BR sem marcadores |
| `stereotype_type_br` | str | Categoria adaptada (ver valores abaixo) |
| `legal_status_br` | str | Enquadramento legal brasileiro |
| `lei_referencia_br` | str | Lei específica aplicável |
| `confianca_traducao_br` | float 0–1 | Score de confiabilidade da adaptação |
| `decision_id` | str | ID rastreável no `adaptation-decisions.md` |

### Valores de `stereotype_type_br`

Inclui as categorias originais mais duas novas para o contexto brasileiro:

| Valor | Descrição |
|---|---|
| `race` | Raça, cor, etnia, origem étnica ou nacional |
| `gender` | Gênero e papéis de gênero |
| `profession` | Profissão ou ocupação |
| `religion` | Religião ou crença |
| `regiao` | **Nova** — Discriminação regional (nordestinos, nortistas…) |
| `orientacao_sexual` | **Nova** — Orientação sexual / identidade de gênero (STF ADO 26) |

### Valores de `legal_status_br`

| Valor | Base legal |
|---|---|
| `crime_racismo` | Lei 7.716/1989, Lei 14.532/2023, STF ADO 26/2019 |
| `crime_trabalho` | Lei 9.029/1995 |
| `vies_cultural` | Preconceito sem tipificação penal clara (incl. discriminação regional) |
| `neutro` | Sem conteúdo discriminatório relevante |

### Score de confiança (`confianca_traducao_br`)

Calculado pelo modelo a partir de três fatores:

| Fator | Peso | Critério |
|---|---|---|
| Equivalência linguística | 40% | Correspondência semântica EN→PT-BR sem perda de sentido |
| Alinhamento jurídico | 40% | Certeza na classificação do `legal_status_br` |
| Transferência cultural | 20% | Equivalência do grupo/estereótipo no contexto brasileiro |

Linhas com score < 0,5 são sinalizadas pela validação para revisão humana.

## Marco Legal Brasileiro (verificado via Chain of Verification)

| Lei | Escopo | Observações |
|---|---|---|
| CF/1988 Art. 3º IV | Vedação geral de discriminação por origem, raça, sexo, cor, idade | Norma programática |
| CF/1988 Art. 5º XLI e XLII | Racismo: inafiançável e imprescritível | Base constitucional |
| Lei 7.716/1989 | Crimes por raça, cor, etnia, religião, procedência nacional | Art. 20: praticar/induzir/incitar discriminação |
| Lei 14.532/2023 Art. 2-A | Injúria por raça/cor/etnia/procedência = racismo (2–5 anos) | **Religião NÃO está no Art. 2-A** — permanece no CP Art. 140 §3º (1–3 anos, prescritível) |
| STF ADO 26/2019 | Homofobia e transfobia = crime de racismo sob Lei 7.716/1989 | Orienta a categoria `orientacao_sexual` |
| Lei 9.029/1995 (red. Lei 13.146/2015) | Discriminação no trabalho | Grounds: sexo, origem, raça, cor, estado civil, **situação familiar**, deficiência, reabilitação profissional, idade |
| Discriminação regional | Sem tipificação penal federal específica | Reconhecida como xenofobia interna via CF/88 Art. 3º IV; usar `vies_cultural` |
| Lei 7.716/1989 + Candomblé/Umbanda | Intolerância religiosa = crime | Religiões de matriz africana protegidas |

> **Nota:** As afirmações desta tabela foram verificadas pelo método Chain of Verification (CoVe) com pesquisa em fontes primárias (Planalto, STF). Duas incorreções foram encontradas e corrigidas: (1) escopo do Art. 2-A excluindo religião; (2) omissão de "situação familiar" na Lei 9.029/1995.

## Como usar

### Pré-requisitos

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### Configuração de chaves de API

O script carrega automaticamente as chaves do arquivo `.env` (se existir) ou das variáveis de ambiente:

```bash
cp .env.example .env
# edite .env e preencha a(s) chave(s) que for usar
```

### Processamento

```bash
# Anthropic (padrão) — modelo mais econômico
.venv/bin/python adapt_dataset.py --input train-MGS.csv

# Ollama local (sem chave)
.venv/bin/python adapt_dataset.py --provider ollama --model llama3.2:latest

# LM Studio local
.venv/bin/python adapt_dataset.py --provider lmstudio --model <nome-do-modelo>

# Groq
.venv/bin/python adapt_dataset.py --provider groq

# Maritaca (modelo brasileiro)
.venv/bin/python adapt_dataset.py --provider maritaca --model sabia-3

# Endpoint OpenAI-compatible customizado
.venv/bin/python adapt_dataset.py --provider custom \
    --base-url http://meu-servidor/v1 --api-key minha-chave --model meu-modelo

# Processar ambos os arquivos (treino + teste) em paralelo
.venv/bin/python adapt_dataset.py --input all --workers 4

# Retomar processamento interrompido
.venv/bin/python adapt_dataset.py --input train-MGS.csv --resume

# Reprocessar apenas as linhas que ficaram sem tradução
.venv/bin/python adapt_dataset.py --input train-MGS.csv --retry-failed

# Amostra para teste rápido
.venv/bin/python adapt_dataset.py --sample 20 --batch-size 5

# Modo verbose para debug (exibe respostas brutas do LLM)
.venv/bin/python adapt_dataset.py --sample 20 --verbose
```

### Parâmetros completos

```
--input ARQUIVO      CSV de entrada em dataset/ (default: train-MGS.csv). Use 'all' para ambos.
--provider           anthropic | openai | groq | maritaca | ollama | lmstudio | custom
--model MODELO       Sobrepõe o modelo padrão do provedor
--base-url URL       URL base do endpoint (obrigatório para --provider custom)
--api-key CHAVE      Sobrepõe a variável de ambiente do provedor
--sample N           Processar apenas as N primeiras linhas
--batch-size N       Linhas por chamada de API (default: 5)
--workers N          Requisições paralelas ao LLM (default: 4)
--resume             Retoma a partir do último checkpoint
--retry-failed       Como --resume, mas também reprocessa linhas sem tradução
--no-parquet         Não gera a versão .parquet da saída
--verbose            Exibe respostas brutas do LLM no console (modo debug)
```

### Validação

```bash
.venv/bin/python validate_adapted.py dataset/train-MGS-BR.csv   # um arquivo
.venv/bin/python validate_adapted.py --all                      # todos os *-MGS-BR.csv
.venv/bin/python validate_adapted.py --all --strict             # atenções viram exit 1
.venv/bin/python validate_adapted.py --all --json relatorio.json
```

A validação reporta (exit code 1 quando há erros — utilizável em CI):
- Colunas novas presentes e contagem de linhas vs. arquivo original
- Distribuição de categorias antes/depois e cobertura de `regiao` / `orientacao_sexual`
- Distribuição do score de confiança
- `stereotype_type_br` / `legal_status_br` fora do schema
- Unicidade de `decision_id`
- Preservação dos `===marcadores===` nas traduções
- Status criminal sem referência legal específica (ex.: `Lei` truncada)
- Linhas `unrelated` classificadas como crime
- Linhas sem tradução (reprocessáveis com `--retry-failed`)

## Arquitetura

A implementação vive no pacote `mgsbr/`; `adapt_dataset.py` e `validate_adapted.py`
são apenas pontos de entrada finos (compatíveis com os comandos antigos).

```
mgsbr/
├── providers.py   — presets de 7 provedores + LLMClient (Anthropic SDK / OpenAI-compatible)
│                    retry de erros transitórios (429/5xx/timeout) com backoff exponencial
│                    + jitter, respeito a retry-after, e contagem de tokens (usage)
├── prompts.py     — system prompt, template de batch, marco legal e PROMPT_VERSION
│                    (hash sha256 dos prompts, gravado nos manifestos .run.json)
├── parsing.py     — strip de fences markdown, normalização de JSON (json-repair),
│                    TYPE_NORM (chaves PT-BR → EN) e schemas válidos
├── checkpoint.py  — checkpoint JSONL incremental e thread-safe; arquiva checkpoints
│                    antigos em execuções sem --resume; só linhas respondidas são gravadas
├── adapter.py     — DatasetAdapter:
│                    adapt_batch()  valida os IDs retornados e refaz retry apenas dos
│                                   faltantes; respostas parciais não perdem linhas
│                    merge_results() une resposta da API com a linha original
│                    process_file() paraleliza via ThreadPoolExecutor/as_completed,
│                                   grava CSV + parquet + manifesto .run.json
│                    save_decision_log() gera adaptation-decisions-<stem>.md
├── validate.py    — validação com exit code, --all, --strict e relatório --json
├── datacard.py    — gera dataset/README.md a partir dos CSVs e manifestos
├── cli.py         — argumentos CLI e orquestração (adapter novo por arquivo)
└── runtime.py     — logging, sinais SIGTERM/SIGINT e evento de shutdown
```

### Testes

```bash
make setup-dev   # instala pytest e ruff
make test        # suíte completa (LLM falso, sem rede)
make lint        # ruff
```

A suíte cobre parsing, retry por IDs faltantes, integridade do checkpoint
(linhas falhas não são marcadas como processadas), `--resume`/`--retry-failed`,
arquivamento de checkpoints antigos e a validação.

### Logging e tolerância a falhas

- **Console**: nível WARNING (apenas erros e retries), sobe para DEBUG com `--verbose`
- **Arquivo**: `logs/adapt_dataset.log` com nível DEBUG (todas as requisições, respostas brutas em falhas)
- **Sinais**: handlers de `SIGTERM`/`SIGINT` salvam checkpoint antes de sair
- **Métricas**: ao final, exibe contagem de batches ok, reparados, parciais e falhos, distribuição de confiança e tokens consumidos por arquivo

### Execução em background

```bash
./run_background.sh   # inicia adapt_dataset.py via nohup, salva PID em logs/adapt.pid
```

## Decisões de implementação

### Suporte multi-provedor (OpenAI-compatible)
Todos os provedores exceto Anthropic usam o SDK `openai` com `base_url` personalizada. O `LLMClient` faz lazy import do SDK relevante, portanto o script funciona se apenas um dos dois SDKs estiver instalado. Provedores locais (Ollama, LM Studio) usam `api_key="no-key-required"` como placeholder.

### Processamento paralelo
Batches são submetidos via `ThreadPoolExecutor` com workers configuráveis (`--workers N`, default 4). Cada thread chama o LLM independentemente. Escrita no checkpoint usa `threading.Lock` para thread-safety. O progresso é atualizado na thread principal conforme cada batch completa (`tqdm`). Falhas em batches individuais são capturadas sem travar os demais.

### Validação estrutural de JSON
A função `_normalize_parsed_json()` garante que a resposta do LLM seja sempre `list[dict]`: objetos únicos são envelopados em array, listas mistas têm elementos não-dict filtrados, e tipos inválidos (`str`, `int`, `None`) disparam retry. Combinada com `json-repair`, a taxa de recuperação de JSON malformado é significativamente maior.

### Normalização de `stereotype_type_br`
Modelos menores (testado com `llama3.2:latest`) ignoram a instrução de usar chaves EN e traduzem para PT-BR (`raça`, `gênero`, `profissão`). O dicionário `_TYPE_NORM` em `merge_results()` converte esses valores de volta às chaves esperadas antes de escrever no CSV.

### Proteção contra valores nulos
Todos os acessos a campos do JSON vindos do LLM usam o padrão `or default` em vez de `.get(key, default)`, pois modelos frequentemente retornam `null` nos campos: `api.get("stereotype_type_br") or "race"`. O helper `_safe_float()` converte `None`, strings vazias e strings não numéricas para `0.0`.

### Validação de `legal_status_br`
Valores fora do schema (ex: `"unrelated"`) são silenciosamente substituídos por `"neutro"`. O `validate_adapted.py` os detecta no CSV caso o fallback falhe.

### Checkpoint por arquivo
Cada execução grava um JSONL em `.checkpoints/<stem>_checkpoint.jsonl`. O flag `--resume` lê o checkpoint e pula as linhas já processadas, permitindo retomada após falhas de rede ou interrupções. O checkpoint é lido inteiro ao final para reconstruir o CSV, garantindo ordem estável independente da ordem de conclusão dos batches paralelos.

Duas regras de integridade:
- **Só linhas respondidas pela API entram no checkpoint.** Lotes que falham após todos os retries permanecem pendentes e são reprocessados no próximo `--resume` (antes, eram gravados com tradução vazia e nunca mais reprocessados).
- **Execuções sem `--resume` arquivam o checkpoint anterior** em `*.bak-<timestamp>` em vez de misturá-lo silenciosamente à nova execução (possivelmente de outro modelo/provedor).

### Validação de IDs por lote
`adapt_batch()` compara os IDs retornados pelo modelo com os solicitados. Se o modelo devolver menos objetos ou IDs trocados, apenas as linhas faltantes são reenviadas no retry — respostas parciais não desperdiçam o que já veio correto, e objetos com IDs desconhecidos são descartados com log.

### Manifesto de execução (proveniência)
Cada arquivo processado gera um `dataset/<stem>-MGS-BR.run.json` com provedor, modelo, hash da versão do prompt, parâmetros, métricas de batches, distribuição de confiança e tokens consumidos. Permite saber exatamente como cada saída foi produzida e estimar o custo do dataset completo a partir de um `--sample`.

### Logging e observabilidade
Logging estruturado com `logging` da stdlib: console em nível WARNING (sobe para DEBUG com `--verbose`), arquivo em nível DEBUG em `logs/adapt_dataset.log`. Em caso de falha de parsing, os primeiros 500 caracteres da resposta bruta do LLM são registrados no arquivo de log. Métricas de batch (ok/reparados/falhos) são exibidas ao final de cada arquivo.

### Score de confiança zero
Linhas do batch cuja resposta JSON foi irrecuperável após 3 retries ficam com `confianca_traducao_br = 0.0` e campos BR vazios no CSV final — mas **não** entram no checkpoint, então `--resume` ou `--retry-failed` as reprocessa. O `validate_adapted.py` sinaliza essas linhas como `← revisar manualmente`.

### Rate limit e erros transitórios
Erros 429/5xx/timeout são tratados no `LLMClient` com backoff exponencial + jitter (até 8 tentativas, teto de 60s), respeitando o header `retry-after` quando o SDK o expõe. Esse retry é separado do retry de parsing JSON, portanto um rate limit não consome as tentativas do lote.

### Diferença EN→PT-BR na classificação legal
O dataset original usa categorias americanas (Civil Rights Act, Equal Pay Act). A adaptação reclassifica conforme a legislação brasileira. Casos sem equivalente cultural claro recebem `vies_cultural` e `confianca_traducao_br < 0.5`.

## Saídas geradas

| Arquivo | Conteúdo |
|---|---|
| `dataset/<stem>-MGS-BR.csv` | Dataset adaptado (train, test ou sample) |
| `dataset/<stem>-MGS-BR.parquet` | Mesma saída em parquet (desative com `--no-parquet`) |
| `dataset/<stem>-MGS-BR.run.json` | Manifesto de proveniência da execução |
| `dataset/adaptation-decisions-<stem>.md` | Log de decisões por arquivo, agrupado por classe |
| `dataset/README.md` | Datacard gerado por `make datacard` |
| `.checkpoints/*.jsonl` | Checkpoints para retomada (preservados por `make clean`; removidos só por `make clean-all`) |
| `logs/adapt_dataset.log` | Log detalhado de execução (nível DEBUG) |
| `logs/adapt_*.log` | Log de execuções em background |

## Dependências

| Pacote | Versão | Finalidade |
|---|---|---|
| `anthropic` | 0.107.1 | SDK para Claude (opcional se usar outro provedor) |
| `openai` | 2.41.0 | SDK para OpenAI e endpoints compatíveis |
| `pandas` | 2.2.3 | Leitura/escrita de CSV |
| `pyarrow` | 19.0.1 | Exportação parquet |
| `python-dotenv` | 1.2.1 | Carregamento de `.env` |
| `json-repair` | 0.54.2 | Reparo automático de JSON malformado |
| `tqdm` | 4.68.1 | Barra de progresso |

Dependências de desenvolvimento (`requirements-dev.txt`): `pytest`, `ruff`.

## Resultado do teste com Ollama (`llama3.2:latest`, 10 linhas)

Dois ciclos de teste executados — o segundo com as correções de normalização aplicadas.

| Métrica | 1º ciclo (sem fix) | 2º ciclo (com fix) |
|---|---|---|
| Linhas processadas | 10 / 10 | 10 / 10 |
| Batches (batch-size=5) | 2 | 2 |
| Retries JSON | 1 | 0 |
| `stereotype_type_br` válidos | 0 / 10 ❌ | 10 / 10 ✅ |
| `legal_status_br` inválidos | 1 (`"unrelated"`) | 0 ✅ |
| Confiança média | 0,59 | 0,51 |
| Alta (≥0,9) | 3 (30%) | 2 (20%) |
| Moderada (0,7–0,89) | 3 (30%) | 2 (20%) |
| Baixa (<0,5) | 3 (30%) | 3 (30%) — revisar |
| Decisões no log | 10 | 10 |

**Problema detectado no 1º ciclo e corrigido:** `llama3.2:latest` ignorou a instrução de usar chaves EN e retornou `raça`, `gênero`, `profissão`. O dicionário `_TYPE_NORM` em `merge_results()` corrige isso automaticamente a partir do 2º ciclo.

**Limitação de qualidade do llama3.2:** classificou estereótipos de gênero como `crime_racismo` com referência a leis de raça. Para o dataset completo, recomenda-se um modelo maior (`gemma3:27b`, `sabia-3`, `claude-haiku-4-5`).

> **Nota:** O modelo padrão do provedor Ollama no script foi atualizado para `qwen2.5:7b`. Para usar `llama3.2`, execute `make sample OLLAMA_MODEL=llama3.2:latest` ou passe `--model llama3.2:latest`.

## Histórico de alterações

Veja [CHANGELOG.md](CHANGELOG.md) para o registro completo de mudanças do projeto.
