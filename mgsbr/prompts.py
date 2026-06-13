"""Prompts do pipeline e versão derivada (hash) para proveniência nos manifestos."""

import hashlib

LEGAL_FRAMEWORK = """
## Marco Legal Brasileiro Relevante

1. **CF/1988, Art. 3º IV e 5º XLI/XLII**: veda toda discriminação por raça, cor, sexo, origem. Racismo é inafiançável e imprescritível.
2. **Lei 7.716/1989 (Lei do Crime Racial)**: tipifica crimes por raça, cor, etnia, religião e procedência nacional.
3. **Lei 14.532/2023**: Art. 2-A na Lei 7.716/1989 — injúria em razão de raça, cor, etnia ou procedência nacional = crime de racismo (pena 2-5 anos, inafiançável, imprescritível). ATENÇÃO: religião NÃO consta do Art. 2-A; injúria por religião permanece no CP Art. 140 §3º (pena 1-3 anos, prescritível).
4. **STF ADO 26/2019**: homofobia e transfobia = crime de racismo (Lei 7.716/1989).
5. **Lei 9.029/1995** (redação da Lei 13.146/2015): proíbe discriminação no trabalho por sexo, origem, raça, cor, estado civil, situação familiar, deficiência, reabilitação profissional, idade, entre outros.
6. **Discriminação regional**: sem tipificação federal específica; reconhecida como xenofobia interna (CF/88 Art. 3º IV).
7. **Religiões de matriz africana (Candomblé, Umbanda)**: protegidas pela Lei 7.716/1989.
"""

SYSTEM_PROMPT = f"""Você é um especialista em direito antidiscriminatório brasileiro e linguística do português do Brasil.
Sua tarefa é adaptar frases de um dataset de estereótipos (originalmente em inglês, contexto americano) para o contexto jurídico-cultural brasileiro.

{LEGAL_FRAMEWORK}

## Categorias de stereotype_type disponíveis (PT-BR):
Use EXATAMENTE estas chaves em inglês (sem tradução, sem acento):
- race              : raça, cor, etnia, origem étnica ou nacional
- gender            : gênero (masculino/feminino, papéis de gênero)
- profession        : profissão ou ocupação
- religion          : religião ou crença
- regiao            : discriminação regional brasileira (nordestinos, nortistas…) — NOVA
- orientacao_sexual : orientação sexual e identidade de gênero (gay, trans…) — NOVA

## Valores de legal_status_br:
- crime_racismo  : conduta tipificada na Lei 7.716/1989, Lei 14.532/2023 ou ADO 26/2019
- crime_trabalho : conduta tipificada na Lei 9.029/1995
- vies_cultural  : preconceito sem tipificação penal clara (inclui discriminação regional)
- neutro         : sem conteúdo discriminatório relevante

## Cálculo de confianca_traducao_br (0.0 a 1.0):
Combine:
- equivalencia_linguistica (40%): correspondência semântica EN→PT-BR sem perda de sentido
- alinhamento_juridico (40%): certeza na classificação legal brasileira
- transferencia_cultural (20%): equivalência do grupo/estereótipo no contexto brasileiro

## Classes de decisão:
- substituicao_grupo       : grupo americano substituído por equivalente brasileiro
- nova_categoria           : categoria regiao ou orientacao_sexual identificada
- reclassificacao_juridica : enquadramento legal mudou vs. original americano
- adaptacao_geografica     : referência geográfica adaptada ao Brasil
- manutencao               : mantido sem mudança significativa
- descarte                 : sem equivalente cultural — marcar confianca < 0.3

Responda EXCLUSIVAMENTE em JSON válido, sem markdown, sem texto fora do JSON.

## REGRA CRÍTICA — Formato JSON
- Todas as chaves do JSON DEVEM permanecer em INGLÊS (ex: "stereotype_type_br", NUNCA "tipo_estereotipo_br").
- Não use acentos, ç, ou caracteres não-ASCII nos nomes das chaves.
- Não adicione vírgulas extras (vírgula final no último elemento de cada objeto NÃO é permitida).
- Todas as strings DEVEM usar aspas duplas ("), nunca aspas simples (').
- Caracteres especiais dentro de strings (aspas, backslashes) DEVEM ser escapados com \\."""

BATCH_PROMPT_TEMPLATE = """Adapte as seguintes {n} linhas do dataset de estereótipos para o contexto brasileiro.

Cada linha tem:
- id: identificador interno
- text_with_marker: texto com ===palavra=== marcada
- text_no_marker: mesmo texto sem marcadores
- label: stereotype | anti-stereotype | unrelated
- stereotype_type: categoria original (EN)

Retorne um JSON array com {n} objetos, um por linha, na mesma ordem:
[
  {{
    "id": "<id da linha>",
    "text_with_marker_br": "<tradução PT-BR preservando ===marcadores===>",
    "text_no_marker_br": "<tradução PT-BR sem marcadores>",
    "stereotype_type_br": "<categoria PT-BR>",
    "legal_status_br": "<status legal>",
    "lei_referencia_br": "<ex: 'Lei 7.716/1989 Art. 20' ou 'neutro'>",
    "confianca_traducao_br": <número 0.0-1.0>,
    "decision_class": "<classe de decisão>",
    "decision_justificativa": "<justificativa em 1-2 frases>"
  }}
]

CRÍTICO: O array deve ter EXATAMENTE {n} objetos, nem mais nem menos. Chaves do JSON em INGLÊS. Sem vírgula final no último campo de cada objeto. Strings com aspas duplas, escapadas com \\.

Linhas a adaptar:
{rows_json}
"""

# Tabela usada no rodapé do decision log e no datacard.
LEGAL_TABLE_MD = [
    "| Lei | Escopo |",
    "|---|---|",
    "| CF/1988 Art. 3º IV e 5º XLI/XLII | Vedação geral de discriminação; racismo inafiançável |",
    "| Lei 7.716/1989 | Crimes de discriminação por raça, cor, etnia, religião, procedência nacional |",
    "| Lei 14.532/2023 Art. 2-A | Injúria por raça/cor/etnia/procedência = racismo (2-5 anos). Religião NÃO inclusa — permanece no CP Art. 140 §3º |",
    "| STF ADO 26/2019 | Homofobia e transfobia = crime de racismo |",
    "| Lei 9.029/1995 (red. Lei 13.146/2015) | Discriminação no trabalho: sexo, raça, cor, estado civil, situação familiar, deficiência, reabilitação profissional, idade |",
]

# Identifica a versão dos prompts nos manifestos .run.json: se o prompt mudar,
# o hash muda, permitindo saber com qual versão cada saída foi gerada.
PROMPT_VERSION = hashlib.sha256(
    (SYSTEM_PROMPT + BATCH_PROMPT_TEMPLATE).encode("utf-8")
).hexdigest()[:12]
