# MGS-BR — Datacard

Adaptação do dataset **MGS (Multi-Grain Stereotypes)** para o contexto
jurídico-cultural brasileiro: tradução EN→PT-BR e classificação conforme a
legislação antidiscriminatória vigente. Gerado automaticamente por
`python -m mgsbr.datacard` — não edite manualmente.

_Atualizado em: 2026-06-12 22:23_

## Schema

| Coluna | Tipo | Descrição |
|---|---|---|
| `text_with_marker` | str | Texto original (EN) com `===palavra===` marcada |
| `text_no_marker` | str | Texto original (EN) sem marcadores |
| `label` | str | `stereotype` \| `anti-stereotype` \| `unrelated` |
| `stereotype_type` | str | Categoria original (EN) |
| `binary_class` / `multi_class` | str | Classes do dataset MGS original |
| `original_dataset` | str | Fonte (StereoSet, CrowS-Pairs) |
| `text_with_marker_br` | str | Tradução PT-BR preservando `===marcadores===` |
| `text_no_marker_br` | str | Tradução PT-BR sem marcadores |
| `stereotype_type_br` | str | Categoria adaptada (inclui `regiao`, `orientacao_sexual`) |
| `legal_status_br` | str | `crime_racismo` \| `crime_trabalho` \| `vies_cultural` \| `neutro` |
| `lei_referencia_br` | str | Lei específica aplicável (ex.: `Lei 7.716/1989 Art. 20`) |
| `confianca_traducao_br` | float 0–1 | Score de confiabilidade da adaptação |
| `decision_id` | str | ID rastreável no log de decisões |

## `sample-MGS-BR.csv`

- **Linhas:** 10
- **Confiança média:** 0.505 (baixa <0.5: 3 linhas)

### Distribuição `stereotype_type_br`

| Valor | Linhas | % |
|---|---|---|
| `race` | 5 | 50.0% |
| `gender` | 3 | 30.0% |
| `profession` | 2 | 20.0% |

### Distribuição `legal_status_br`

| Valor | Linhas | % |
|---|---|---|
| `vies_cultural` | 4 | 40.0% |
| `crime_racismo` | 3 | 30.0% |
| `neutro` | 2 | 20.0% |
| `crime_trabalho` | 1 | 10.0% |

## `train-MGS-BR.csv`

- **Linhas:** 10
- **Confiança média:** 0.705 (baixa <0.5: 2 linhas)

### Distribuição `stereotype_type_br`

| Valor | Linhas | % |
|---|---|---|
| `race` | 4 | 40.0% |
| `gender` | 2 | 20.0% |
| `neutro` | 2 | 20.0% |
| `profession` | 2 | 20.0% |

### Distribuição `legal_status_br`

| Valor | Linhas | % |
|---|---|---|
| `neutro` | 7 | 70.0% |
| `vies_cultural` | 3 | 30.0% |

## Marco Legal Consultado

| Lei | Escopo |
|---|---|
| CF/1988 Art. 3º IV e 5º XLI/XLII | Vedação geral de discriminação; racismo inafiançável |
| Lei 7.716/1989 | Crimes de discriminação por raça, cor, etnia, religião, procedência nacional |
| Lei 14.532/2023 Art. 2-A | Injúria por raça/cor/etnia/procedência = racismo (2-5 anos). Religião NÃO inclusa — permanece no CP Art. 140 §3º |
| STF ADO 26/2019 | Homofobia e transfobia = crime de racismo |
| Lei 9.029/1995 (red. Lei 13.146/2015) | Discriminação no trabalho: sexo, raça, cor, estado civil, situação familiar, deficiência, reabilitação profissional, idade |

## Logs de decisão

Cada arquivo possui um log `adaptation-decisions-<stem>.md` com as decisões
de adaptação agrupadas por classe (substituição de grupo, nova categoria,
reclassificação jurídica, adaptação geográfica, manutenção, descarte).
