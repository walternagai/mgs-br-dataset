# MGS-BR — Adaptação do Dataset Multi-Grain Stereotypes para o Contexto Brasileiro

Converte o dataset **MGS** (Multi-Grain Stereotypes) — originalmente em inglês e centrado na realidade americana — para o **contexto jurídico-cultural brasileiro**, traduzindo os textos para PT-BR e acrescentando colunas de classificação legal conforme a legislação vigente.

## Quick Start

```bash
# 1. Clone e configure o ambiente
git clone <repo-url> && cd mgs-br-dataset
make setup

# 2. Teste o pipeline em 20 linhas (requer Ollama — https://ollama.com)
ollama pull qwen2.5:7b
make sample

# 3. Para processar os datasets completos (requer chave da API)
export ANTHROPIC_API_KEY=sk-ant-...
python adapt_dataset.py --input train-MGS.csv --resume
python adapt_dataset.py --input test-MGS.csv --resume
```

**Sem Ollama?** Qualquer provedor OpenAI-compatible funciona. Veja a seção [Como usar](#como-usar) abaixo.

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
.venv/bin/pip install anthropic openai pandas tqdm
```

### Processamento

```bash
# Anthropic (padrão) — modelo mais econômico
export ANTHROPIC_API_KEY="sk-ant-..."
.venv/bin/python adapt_dataset.py --input train-MGS.csv

# Ollama local (sem chave)
.venv/bin/python adapt_dataset.py --provider ollama --model llama3.2:latest

# LM Studio local
.venv/bin/python adapt_dataset.py --provider lmstudio --model <nome-do-modelo>

# Groq
export GROQ_API_KEY="gsk_..."
.venv/bin/python adapt_dataset.py --provider groq

# Maritaca (modelo brasileiro)
export MARITACA_API_KEY="..."
.venv/bin/python adapt_dataset.py --provider maritaca --model sabia-3

# Endpoint OpenAI-compatible customizado
.venv/bin/python adapt_dataset.py --provider custom \
    --base-url http://meu-servidor/v1 --api-key minha-chave --model meu-modelo

# Processar ambos os arquivos
.venv/bin/python adapt_dataset.py --input all

# Retomar processamento interrompido
.venv/bin/python adapt_dataset.py --input train-MGS.csv --resume

# Amostra para teste rápido
.venv/bin/python adapt_dataset.py --sample 20 --batch-size 5
```

### Parâmetros completos

```
--input ARQUIVO      CSV de entrada em dataset/ (default: train-MGS.csv). Use 'all' para ambos.
--provider           anthropic | openai | groq | maritaca | ollama | lmstudio | custom
--model MODELO       Sobrepõe o modelo padrão do provedor
--base-url URL       URL base do endpoint (obrigatório para --provider custom)
--api-key CHAVE      Sobrepõe a variável de ambiente do provedor
--sample N           Processar apenas as N primeiras linhas
--batch-size N       Linhas por chamada de API (default: 10)
--resume             Retoma a partir do último checkpoint
```

### Validação

```bash
.venv/bin/python validate_adapted.py dataset/train-MGS-BR.csv
.venv/bin/python validate_adapted.py dataset/test-MGS-BR.csv
```

A validação reporta:
- Distribuição de categorias antes/depois
- Cobertura das novas categorias (`regiao`, `orientacao_sexual`)
- Distribuição do score de confiança
- Linhas com `legal_status_br` fora do schema
- Linhas com `stereotype_type_br` inválido

## Arquitetura do script

```
adapt_dataset.py
│
├── PROVIDERS dict          — presets de 7 provedores (url, modelo padrão, env var)
├── _TYPE_NORM dict         — normaliza chaves PT-BR para EN (robustez a modelos menores)
├── _VALID_TYPES / _VALID_LEGAL — schemas válidos com fallback em merge_results()
│
├── LLMClient               — abstração sobre Anthropic SDK e OpenAI SDK
│   ├── _call_anthropic()   — usa messages.create() com system separado
│   └── _call_openai()      — usa chat.completions.create() com system em messages[]
│
├── DatasetAdapter
│   ├── adapt_batch()       — chama LLMClient, faz strip de markdown, parse JSON
│   │                         retry automático (3x, backoff linear)
│   ├── merge_results()     — une resposta da API com linha original
│   │                         aplica _TYPE_NORM e validação de _VALID_LEGAL
│   ├── process_file()      — lê CSV, segmenta em batches, escreve checkpoint JSONL,
│   │                         reconstrói CSV na ordem original
│   └── save_decision_log() — gera adaptation-decisions.md agrupado por classe
│
├── resolve_llm()           — resolve provedor, modelo, chave e base_url
└── main()                  — parse de args, orquestra o pipeline
```

## Decisões de implementação

### Suporte multi-provedor (OpenAI-compatible)
Todos os provedores exceto Anthropic usam o SDK `openai` com `base_url` personalizada. O `LLMClient` faz lazy import do SDK relevante, portanto o script funciona se apenas um dos dois SDKs estiver instalado. Provedores locais (Ollama, LM Studio) usam `api_key="no-key-required"` como placeholder.

### Normalização de `stereotype_type_br`
Modelos menores (testado com `llama3.2:latest`) ignoram a instrução de usar chaves EN e traduzem para PT-BR (`raça`, `gênero`, `profissão`). O dicionário `_TYPE_NORM` em `merge_results()` converte esses valores de volta às chaves esperadas antes de escrever no CSV.

### Validação de `legal_status_br`
Valores fora do schema (ex: `"unrelated"`) são silenciosamente substituídos por `"neutro"`. O `validate_adapted.py` os detecta no CSV caso o fallback falhe.

### Checkpoint por arquivo
Cada execução grava um JSONL em `.checkpoints/<stem>_checkpoint.jsonl`. O flag `--resume` lê o checkpoint e pula as linhas já processadas, permitindo retomada após falhas de rede ou interrupções.

### Score de confiança zero
Linhas do batch cuja resposta JSON foi irrecuperável após 3 retries ficam com `confianca_traducao_br = 0.0` e campos BR vazios. O `validate_adapted.py` sinaliza essas linhas como `← revisar manualmente`.

### Diferença EN→PT-BR na classificação legal
O dataset original usa categorias americanas (Civil Rights Act, Equal Pay Act). A adaptação reclassifica conforme a legislação brasileira. Casos sem equivalente cultural claro recebem `vies_cultural` e `confianca_traducao_br < 0.5`.

## Saídas geradas

| Arquivo | Conteúdo |
|---|---|
| `dataset/train-MGS-BR.csv` | Dataset de treino adaptado |
| `dataset/test-MGS-BR.csv` | Dataset de teste adaptado |
| `dataset/sample-MGS-BR.csv` | Amostra de teste adaptada |
| `dataset/adaptation-decisions.md` | Log de decisões agrupado por classe |
| `.checkpoints/*.jsonl` | Checkpoints para retomada (podem ser removidos após conclusão) |

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
