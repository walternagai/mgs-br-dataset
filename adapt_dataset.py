#!/usr/bin/env python3
"""
Adapta o dataset MGS (Multi-Grain Stereotypes) para o contexto jurídico-cultural brasileiro,
traduzindo textos EN→PT-BR e acrescentando colunas de classificação legal.

Saída: dataset/<stem>-MGS-BR.csv  +  dataset/adaptation-decisions.md

Uso: .venv/bin/python adapt_dataset.py --help
"""

import os
import sys
import json
import time
import argparse
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from collections import defaultdict
from datetime import datetime

import pandas as pd
from tqdm import tqdm
from dotenv import load_dotenv
from json_repair import repair_json

load_dotenv()

# ---------------------------------------------------------------------------
# Presets de provedores
# ---------------------------------------------------------------------------

PROVIDERS: dict[str, dict] = {
    "anthropic": {
        "sdk":           "anthropic",
        "base_url":      None,
        "default_model": "claude-haiku-4-5-20251001",
        "env_key":       "ANTHROPIC_API_KEY",
        "requires_key":  True,
    },
    "openai": {
        "sdk":           "openai",
        "base_url":      "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "env_key":       "OPENAI_API_KEY",
        "requires_key":  True,
    },
    "groq": {
        "sdk":           "openai",
        "base_url":      "https://api.groq.com/openai/v1",
        "default_model": "llama-3.3-70b-versatile",
        "env_key":       "GROQ_API_KEY",
        "requires_key":  True,
    },
    "maritaca": {
        "sdk":           "openai",
        "base_url":      "https://chat.maritaca.ai/api",
        "default_model": "sabia-4",
        "env_key":       "MARITACA_API_KEY",
        "requires_key":  True,
    },
    "ollama": {
        "sdk":           "openai",
        "base_url":      "http://localhost:11434/v1",
        "default_model": "qwen2.5:7b",
        "env_key":       None,
        "requires_key":  False,
    },
    "lmstudio": {
        "sdk":           "openai",
        "base_url":      "http://localhost:1234/v1",
        "default_model": "local-model",
        "env_key":       None,
        "requires_key":  False,
    },
    "custom": {
        "sdk":           "openai",
        "base_url":      None,          # obrigatório via --base-url
        "default_model": "default",
        "env_key":       None,
        "requires_key":  False,
    },
}

# Modelos menores frequentemente traduzem as chaves para PT-BR; normalizamos aqui.
_TYPE_NORM: dict[str, str] = {
    "raça": "race",        "raca": "race",
    "gênero": "gender",    "genero": "gender",
    "profissão": "profession", "profissao": "profession",
    "religião": "religion","religiao": "religion",
    "região": "regiao",    "orientação sexual": "orientacao_sexual",
    "orientacao sexual": "orientacao_sexual",
}
_VALID_TYPES  = {"race", "gender", "profession", "religion", "regiao", "orientacao_sexual"}
_VALID_LEGAL  = {"crime_racismo", "crime_trabalho", "vies_cultural", "neutro"}

# ---------------------------------------------------------------------------
# Configurações padrão
# ---------------------------------------------------------------------------

DATASET_DIR        = Path("dataset")
CHECKPOINT_DIR     = Path(".checkpoints")
DEFAULT_BATCH_SIZE = 5
DEFAULT_WORKERS   = 4
MAX_RETRIES        = 3
RETRY_DELAY        = 5  # segundos

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Camada de abstração de LLM
# ---------------------------------------------------------------------------

class LLMClient:
    """Wrapper unificado sobre Anthropic SDK e qualquer endpoint OpenAI-compatible."""

    def __init__(self, provider: str, model: str, api_key: str, base_url: str | None):
        self.provider = provider
        self.model    = model
        preset        = PROVIDERS.get(provider, PROVIDERS["custom"])

        if preset["sdk"] == "anthropic":
            try:
                import anthropic as _ant
            except ImportError:
                sys.exit("Erro: instale o SDK Anthropic — .venv/bin/pip install anthropic")
            self._backend = "anthropic"
            self._client  = _ant.Anthropic(api_key=api_key)
        else:
            try:
                import openai as _oai
            except ImportError:
                sys.exit("Erro: instale o SDK OpenAI — .venv/bin/pip install openai")
            self._backend = "openai"
            # Provedores locais (Ollama, LM Studio) não exigem chave real
            self._client  = _oai.OpenAI(
                api_key=api_key or "no-key-required",
                base_url=base_url,
            )

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        if self._backend == "anthropic":
            return self._call_anthropic(system, user, max_tokens)
        return self._call_openai(system, user, max_tokens)

    def _call_anthropic(self, system: str, user: str, max_tokens: int) -> str:
        import anthropic as _ant
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return msg.content[0].text

    def _call_openai(self, system: str, user: str, max_tokens: int) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return resp.choices[0].message.content


def _strip_markdown_fences(text: str) -> str:
    """Remove blocos de código markdown que alguns modelos inserem ao redor do JSON."""
    text = text.strip()
    if text.startswith("```"):
        # remove primeira linha (```json ou ```)
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        # remove fechamento ```
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()


# ---------------------------------------------------------------------------
# Adaptador principal
# ---------------------------------------------------------------------------

class DatasetAdapter:
    def __init__(self, llm: LLMClient):
        self.llm              = llm
        self.decisions: list[dict]        = []
        self.decision_counter: dict[str, int] = defaultdict(int)
        self._lock            = threading.Lock()

    def _row_id(self, row: dict, idx: int) -> str:
        text = row.get("text_no_marker", "")[:50]
        return f"{idx:06d}_{hashlib.md5(text.encode()).hexdigest()[:6]}"

    def adapt_batch(self, batch: list[dict]) -> list[dict]:
        rows_for_api = [
            {
                "id":              b["_id"],
                "text_with_marker": b.get("text_with_marker", ""),
                "text_no_marker":   b.get("text_no_marker", ""),
                "label":            b.get("label", ""),
                "stereotype_type":  b.get("stereotype_type", ""),
            }
            for b in batch
        ]
        prompt = BATCH_PROMPT_TEMPLATE.format(
            n=len(batch),
            rows_json=json.dumps(rows_for_api, ensure_ascii=False, indent=2),
        )

        for attempt in range(MAX_RETRIES):
            try:
                raw = self.llm.complete(SYSTEM_PROMPT, prompt)
                raw = _strip_markdown_fences(raw)
                return json.loads(raw)
            except json.JSONDecodeError as exc:
                err = f"JSON inválido: {exc}"
                # tenta reparo automático antes do retry tradicional
                try:
                    repaired = repair_json(raw)
                    return json.loads(repaired)
                except Exception:
                    pass
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"

            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (attempt + 1)
                print(f"\n  [retry {attempt+1}] {err} — aguardando {wait}s")
                time.sleep(wait)
            else:
                print(f"\n  [falha] lote ignorado após {MAX_RETRIES} tentativas: {err}")
                return []

    def merge_results(self, original_rows: list[dict], api_results: list[dict]) -> list[dict]:
        result_map = {r["id"]: r for r in api_results if "id" in r}
        merged = []
        for row in original_rows:
            rid = row["_id"]
            api = result_map.get(rid, {})
            new_row = {k: v for k, v in row.items() if k != "_id"}

            new_row["text_with_marker_br"]  = api.get("text_with_marker_br", "")
            new_row["text_no_marker_br"]    = api.get("text_no_marker_br", "")

            raw_type = api.get("stereotype_type_br", row.get("stereotype_type", ""))
            new_row["stereotype_type_br"] = _TYPE_NORM.get(raw_type.lower().strip(), raw_type) \
                if raw_type not in _VALID_TYPES else raw_type

            raw_legal = api.get("legal_status_br", "neutro")
            new_row["legal_status_br"]      = raw_legal if raw_legal in _VALID_LEGAL else "neutro"
            new_row["lei_referencia_br"]    = api.get("lei_referencia_br", "neutro")
            new_row["confianca_traducao_br"] = api.get("confianca_traducao_br", 0.0)
            new_row["decision_id"]          = rid

            if api:
                with self._lock:
                    self.decisions.append({
                        "id":                rid,
                        "decision_class":    api.get("decision_class", "manutencao"),
                        "justificativa":     api.get("decision_justificativa", ""),
                        "grupo_original_en": row.get("stereotype_type", ""),
                        "stereotype_type_br": api.get("stereotype_type_br", ""),
                        "legal_status_br":   api.get("legal_status_br", "neutro"),
                        "lei_referencia_br": api.get("lei_referencia_br", "neutro"),
                        "confianca":         api.get("confianca_traducao_br", 0.0),
                        "text_original":     row.get("text_no_marker", "")[:120],
                        "text_br":           api.get("text_no_marker_br", "")[:120],
                    })
                    self.decision_counter[api.get("decision_class", "manutencao")] += 1

            merged.append(new_row)
        return merged

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        sample:     int | None = None,
        resume:     bool = False,
        batch_size: int  = DEFAULT_BATCH_SIZE,
        workers:    int  = DEFAULT_WORKERS,
    ):
        CHECKPOINT_DIR.mkdir(exist_ok=True)
        checkpoint_path = CHECKPOINT_DIR / f"{input_path.stem}_checkpoint.jsonl"

        df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
        if sample:
            df = df.head(sample)
        total = len(df)

        print(f"\n{'='*60}")
        print(f"Processando : {input_path.name}  ({total} linhas)")
        print(f"Provedor    : {self.llm.provider}  |  Modelo: {self.llm.model}")
        print(f"Workers     : {workers}")
        print(f"{'='*60}")

        processed_ids: set[str] = set()
        if resume and checkpoint_path.exists():
            with open(checkpoint_path, encoding="utf-8") as f:
                for line in f:
                    rec = json.loads(line)
                    processed_ids.add(rec.get("decision_id", ""))
            print(f"  Retomando: {len(processed_ids)} linhas já processadas")

        all_rows = df.to_dict("records")
        pending  = []
        for idx, row in enumerate(all_rows):
            rid = self._row_id(row, idx)
            row["_id"] = rid
            if rid not in processed_ids:
                pending.append(row)

        if not pending:
            print("  Nada pendente — todas as linhas já processadas.")
        else:
            batches = [pending[i:i + batch_size] for i in range(0, len(pending), batch_size)]
            workers = min(workers, len(batches))

            checkpoint_file = open(checkpoint_path, "a", encoding="utf-8")
            ckpt_lock        = threading.Lock()

            def _process_batch(batch):
                api_res = self.adapt_batch(batch)
                merged  = self.merge_results(batch, api_res)
                with ckpt_lock:
                    for row in merged:
                        checkpoint_file.write(json.dumps(row, ensure_ascii=False) + "\n")
                return len(batch)

            try:
                with ThreadPoolExecutor(max_workers=workers) as executor:
                    futures = {executor.submit(_process_batch, b): b for b in batches}
                    with tqdm(total=len(pending), desc="  Adaptando", unit="linhas") as pbar:
                        for future in as_completed(futures):
                            batch = futures[future]
                            try:
                                n = future.result()
                            except Exception as exc:
                                n = len(batch)
                                print(f"\n  [erro] batch falhou: {type(exc).__name__}: {exc}")
                            pbar.update(n)
            finally:
                checkpoint_file.close()

        processed_rows: list[dict] = []
        if checkpoint_path.exists():
            with open(checkpoint_path, encoding="utf-8") as f:
                for line in f:
                    processed_rows.append(json.loads(line))

        id_to_result = {r.get("decision_id", ""): r for r in processed_rows}
        final_rows   = []
        for idx, row in enumerate(all_rows):
            rid = self._row_id(row, idx)
            if rid in id_to_result:
                final_rows.append(id_to_result[rid])
            else:
                clean = {k: v for k, v in row.items() if k != "_id"}
                clean.update({
                    "text_with_marker_br":  "",
                    "text_no_marker_br":    "",
                    "stereotype_type_br":   row.get("stereotype_type", ""),
                    "legal_status_br":      "neutro",
                    "lei_referencia_br":    "neutro",
                    "confianca_traducao_br": 0.0,
                    "decision_id":          rid,
                })
                final_rows.append(clean)

        pd.DataFrame(final_rows).to_csv(output_path, index=False)

        def _conf(r): return float(r.get("confianca_traducao_br", 0))
        alta  = sum(1 for r in final_rows if _conf(r) >= 0.9)
        mod_a = sum(1 for r in final_rows if 0.7 <= _conf(r) < 0.9)
        baixa = sum(1 for r in final_rows if _conf(r) < 0.5)

        print(f"\n  Salvo em: {output_path}")
        print(f"  Confianca — alta(>=0.9): {alta} | mod(0.7-0.89): {mod_a} | baixa(<0.5): {baixa}")
        return final_rows

    def save_decision_log(self, output_path: Path):
        by_class: dict[str, list[dict]] = defaultdict(list)
        for d in self.decisions:
            by_class[d["decision_class"]].append(d)

        lines = [
            "# Log de Decisões de Adaptação — MGS Dataset → Contexto Brasileiro",
            "",
            f"**Gerado em:** {datetime.now().strftime('%Y-%m-%d %H:%M')}  ",
            f"**Provedor:** `{self.llm.provider}`  ",
            f"**Modelo:** `{self.llm.model}`  ",
            f"**Total de decisões registradas:** {len(self.decisions)}  ",
            "",
            "---",
            "",
            "## Sumário por Classe de Decisão",
            "",
            "| Classe | Quantidade |",
            "|---|---|",
        ]
        for cls, count in sorted(self.decision_counter.items(), key=lambda x: -x[1]):
            lines.append(f"| `{cls}` | {count} |")

        lines += ["", "---", ""]

        CLASS_LABELS = {
            "substituicao_grupo":       "## Substituição de Grupo Étnico/Nacional",
            "nova_categoria":           "## Criação de Nova Categoria (`regiao` ou `orientacao_sexual`)",
            "reclassificacao_juridica": "## Reclassificação Jurídica",
            "adaptacao_geografica":     "## Adaptação de Referência Geográfica",
            "manutencao":               "## Manutenção sem Mudança Significativa",
            "descarte":                 "## Exemplos Descartados / Baixa Confiança",
        }

        for cls in CLASS_LABELS:
            items = by_class.get(cls, [])
            if not items:
                continue
            lines.append(CLASS_LABELS[cls])
            lines.append("")
            for item in items[:30]:
                lines += [
                    f"### Decisão: `{item['id']}`",
                    f"- **Categoria original (EN):** `{item['grupo_original_en']}`",
                    f"- **Categoria adaptada (PT-BR):** `{item['stereotype_type_br']}`",
                    f"- **Status legal:** `{item['legal_status_br']}`",
                    f"- **Lei referenciada:** {item['lei_referencia_br']}",
                    f"- **Confiança:** {item['confianca']:.2f}",
                    f"- **Texto original (EN):** _{item['text_original']}_",
                    f"- **Texto adaptado (PT-BR):** _{item['text_br']}_",
                    f"- **Justificativa:** {item['justificativa']}",
                    "",
                ]
            if len(items) > 30:
                lines.append(f"_... e mais {len(items) - 30} casos desta classe._")
                lines.append("")
            lines += ["---", ""]

        lines += [
            "## Framework Legal Consultado",
            "",
            "| Lei | Escopo |",
            "|---|---|",
            "| CF/1988 Art. 3º IV e 5º XLI/XLII | Vedação geral de discriminação; racismo inafiançável |",
            "| Lei 7.716/1989 | Crimes de discriminação por raça, cor, etnia, religião, procedência nacional |",
            "| Lei 14.532/2023 Art. 2-A | Injúria por raça/cor/etnia/procedência = racismo (2-5 anos). Religião NÃO inclusa — permanece no CP Art. 140 §3º |",
            "| STF ADO 26/2019 | Homofobia e transfobia = crime de racismo |",
            "| Lei 9.029/1995 (red. Lei 13.146/2015) | Discriminação no trabalho: sexo, raça, cor, estado civil, situação familiar, deficiência, reabilitação profissional, idade |",
        ]

        output_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  Decision log salvo em: {output_path}")


# ---------------------------------------------------------------------------
# Resolução de provedor / chave / modelo
# ---------------------------------------------------------------------------

def resolve_llm(args: argparse.Namespace) -> LLMClient:
    provider = args.provider
    preset   = PROVIDERS.get(provider)
    if preset is None:
        sys.exit(f"Provedor desconhecido: '{provider}'. Opções: {', '.join(PROVIDERS)}")

    base_url = args.base_url or preset["base_url"]
    if provider == "custom" and not base_url:
        sys.exit("Erro: --base-url é obrigatório para --provider custom")

    model   = args.model or preset["default_model"]
    api_key = args.api_key
    if not api_key and preset["env_key"]:
        api_key = os.environ.get(preset["env_key"], "")
    if not api_key and preset["requires_key"]:
        env_var = preset["env_key"] or "API_KEY"
        sys.exit(
            f"Erro: chave de API não encontrada para '{provider}'.\n"
            f"  Defina {env_var} ou use --api-key <chave>."
        )

    return LLMClient(provider=provider, model=model, api_key=api_key, base_url=base_url)


# ---------------------------------------------------------------------------
# Ponto de entrada
# ---------------------------------------------------------------------------

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
        "--workers", type=int, default=DEFAULT_WORKERS, metavar="N",
        help=f"Requisições paralelas ao LLM (default: {DEFAULT_WORKERS})",
    )
    return p


def main():
    args    = build_parser().parse_args()
    llm     = resolve_llm(args)
    adapter = DatasetAdapter(llm)

    decision_log_path = DATASET_DIR / "adaptation-decisions.md"
    input_files = (
        ["train-MGS.csv", "test-MGS.csv"] if args.input == "all" else [args.input]
    )

    for filename in input_files:
        input_path = DATASET_DIR / filename
        if not input_path.exists():
            print(f"Arquivo não encontrado: {input_path}")
            continue
        stem        = input_path.stem.replace("-MGS", "")
        output_path = DATASET_DIR / f"{stem}-MGS-BR.csv"
        adapter.process_file(
            input_path, output_path,
            sample=args.sample, resume=args.resume, batch_size=args.batch_size,
            workers=args.workers,
        )

    adapter.save_decision_log(decision_log_path)
    print("\nConcluído.")


if __name__ == "__main__":
    main()
