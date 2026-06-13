"""Núcleo do pipeline: adaptação em batches, merge, checkpoint e saídas."""

import hashlib
import json
import sys
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from .checkpoint import Checkpoint
from .parsing import TYPE_NORM, VALID_LEGAL, VALID_TYPES, parse_llm_json, safe_float
from .prompts import BATCH_PROMPT_TEMPLATE, LEGAL_TABLE_MD, PROMPT_VERSION, SYSTEM_PROMPT
from .runtime import interruptible_sleep, logger, shutdown_requested

CHECKPOINT_DIR     = Path(".checkpoints")
DEFAULT_BATCH_SIZE = 5
DEFAULT_WORKERS    = 4
MAX_RETRIES        = 3
RETRY_DELAY        = 5  # segundos

# Campos BR vazios usados para linhas ainda não processadas.
EMPTY_BR_FIELDS = {
    "text_with_marker_br":   "",
    "text_no_marker_br":     "",
    "legal_status_br":       "neutro",
    "lei_referencia_br":     "neutro",
    "confianca_traducao_br": 0.0,
}


class DatasetAdapter:
    def __init__(self, llm, checkpoint_dir: Path = CHECKPOINT_DIR):
        self.llm              = llm
        self.checkpoint_dir   = checkpoint_dir
        self.decisions: list[dict]            = []
        self.decision_counter: dict[str, int] = defaultdict(int)
        self._lock            = threading.Lock()
        # métricas de processamento
        self.batches_ok       = 0
        self.batches_repaired = 0
        self.batches_partial  = 0
        self.batches_fail     = 0
        self.rows_failed      = 0

    def _row_id(self, row: dict, idx: int) -> str:
        text = row.get("text_no_marker", "")[:50]
        return f"{idx:06d}_{hashlib.md5(text.encode()).hexdigest()[:6]}"

    def adapt_batch(self, batch: list[dict]) -> list[dict]:
        """Adapta um lote, revalidando os IDs retornados pelo modelo.

        Respostas parciais (menos objetos que o pedido, ou IDs trocados) disparam
        retry apenas das linhas faltantes. Retorna os objetos coletados — que podem
        ser menos que o lote completo em caso de falha definitiva.
        """
        remaining  = list(batch)
        collected: list[dict] = []
        used_repair = False
        attempted   = False
        last_err    = ""
        last_raw    = ""

        for attempt in range(MAX_RETRIES):
            if shutdown_requested.is_set():
                break
            attempted = True

            rows_for_api = [
                {
                    "id":               b["_id"],
                    "text_with_marker": b.get("text_with_marker", ""),
                    "text_no_marker":   b.get("text_no_marker", ""),
                    "label":            b.get("label", ""),
                    "stereotype_type":  b.get("stereotype_type", ""),
                }
                for b in remaining
            ]
            prompt = BATCH_PROMPT_TEMPLATE.format(
                n=len(remaining),
                rows_json=json.dumps(rows_for_api, ensure_ascii=False, indent=2),
            )

            try:
                raw = self.llm.complete(SYSTEM_PROMPT, prompt)
                last_raw = raw
            except Exception as exc:
                last_err = f"{type(exc).__name__}: {exc}"
            else:
                parsed, repaired, err = parse_llm_json(raw)
                if parsed is None:
                    last_err = err
                else:
                    used_repair = used_repair or repaired
                    wanted  = {b["_id"] for b in remaining}
                    matched = [
                        r for r in parsed
                        if isinstance(r.get("id"), str) and r["id"] in wanted
                    ]
                    unknown = len(parsed) - len(matched)
                    if unknown:
                        logger.warning(
                            "Batch %s: %d objetos com id desconhecido descartados",
                            remaining[0]["_id"], unknown,
                        )
                    collected.extend(matched)
                    matched_ids = {r["id"] for r in matched}
                    remaining   = [b for b in remaining if b["_id"] not in matched_ids]
                    if not remaining:
                        with self._lock:
                            if used_repair:
                                self.batches_repaired += 1
                            else:
                                self.batches_ok += 1
                        return collected
                    last_err = f"{len(remaining)} ids sem resposta do modelo"

            if attempt < MAX_RETRIES - 1:
                wait = RETRY_DELAY * (attempt + 1)
                logger.debug(
                    "Retry %d/%d batch %s: %s — aguardando %ds",
                    attempt + 1, MAX_RETRIES,
                    batch[0]["_id"] if batch else "???", last_err, wait,
                )
                if interruptible_sleep(wait):
                    break

        if remaining and attempted and not shutdown_requested.is_set():
            with self._lock:
                if collected:
                    self.batches_partial += 1
                else:
                    self.batches_fail += 1
                self.rows_failed += len(remaining)
            logger.error(
                "Batch incompleto após %d tentativas (%d/%d linhas sem resposta): %s | "
                "resposta (primeiros 500 chars): %s",
                MAX_RETRIES, len(remaining), len(batch), last_err,
                last_raw[:500] if last_raw else "(vazia)",
            )
            print(
                f"\n  [falha] {len(remaining)} linhas sem resposta após "
                f"{MAX_RETRIES} tentativas: {last_err}"
            )
        elif remaining:
            logger.info("Batch interrompido por shutdown com %d linhas pendentes", len(remaining))

        return collected

    def merge_results(self, original_rows: list[dict], api_results: list[dict]) -> list[dict]:
        result_map = {r["id"]: r for r in api_results if isinstance(r, dict) and "id" in r}
        merged = []
        for row in original_rows:
            rid = row["_id"]
            api = result_map.get(rid, {})
            new_row = {k: v for k, v in row.items() if k != "_id"}

            new_row["text_with_marker_br"]  = api.get("text_with_marker_br") or ""
            new_row["text_no_marker_br"]    = api.get("text_no_marker_br") or ""

            raw_type = api.get("stereotype_type_br") or row.get("stereotype_type", "")
            if isinstance(raw_type, str):
                new_row["stereotype_type_br"] = (
                    raw_type if raw_type in VALID_TYPES
                    else TYPE_NORM.get(raw_type.lower().strip(), raw_type)
                )
            else:
                new_row["stereotype_type_br"] = row.get("stereotype_type", "")

            raw_legal = api.get("legal_status_br", "neutro")
            new_row["legal_status_br"]      = raw_legal if raw_legal in VALID_LEGAL else "neutro"
            new_row["lei_referencia_br"]    = api.get("lei_referencia_br") or "neutro"
            new_row["confianca_traducao_br"] = safe_float(api.get("confianca_traducao_br"), 0.0)
            new_row["decision_id"]          = rid

            if api:
                with self._lock:
                    self.decisions.append({
                        "id":                rid,
                        "decision_class":    api.get("decision_class") or "manutencao",
                        "justificativa":     api.get("decision_justificativa") or "",
                        "grupo_original_en": row.get("stereotype_type", ""),
                        "stereotype_type_br": api.get("stereotype_type_br") or "",
                        "legal_status_br":   api.get("legal_status_br") or "neutro",
                        "lei_referencia_br": api.get("lei_referencia_br") or "neutro",
                        "confianca":         safe_float(api.get("confianca_traducao_br"), 0.0),
                        "text_original":     row.get("text_no_marker", "")[:120],
                        "text_br":           (api.get("text_no_marker_br") or "")[:120],
                    })
                    self.decision_counter[api.get("decision_class") or "manutencao"] += 1

            merged.append(new_row)
        return merged

    def process_file(
        self,
        input_path: Path,
        output_path: Path,
        *,
        sample:        int | None = None,
        resume:        bool = False,
        retry_failed:  bool = False,
        batch_size:    int  = DEFAULT_BATCH_SIZE,
        workers:       int  = DEFAULT_WORKERS,
        write_parquet: bool = True,
    ) -> list[dict]:
        checkpoint = Checkpoint(self.checkpoint_dir / f"{input_path.stem}_checkpoint.jsonl")
        started_at = datetime.now()
        usage_start = self._usage_snapshot()

        df = pd.read_csv(input_path, dtype=str, keep_default_na=False)
        if sample:
            df = df.head(sample)
        total = len(df)

        print(f"\n{'='*60}")
        print(f"Processando : {input_path.name}  ({total} linhas)")
        print(f"Provedor    : {self.llm.provider}  |  Modelo: {self.llm.model}")
        print(f"Workers     : {workers}")
        print(f"{'='*60}")
        logger.info(
            "Iniciando: %s (%d linhas) | provider=%s model=%s workers=%d "
            "resume=%s retry_failed=%s sample=%s prompt=%s",
            input_path.name, total, self.llm.provider, self.llm.model,
            workers, resume, retry_failed, sample, PROMPT_VERSION,
        )

        use_checkpoint = resume or retry_failed
        if not use_checkpoint:
            checkpoint.archive()

        processed_ids: set[str] = set()
        if use_checkpoint:
            processed_ids = checkpoint.processed_ids(retry_failed=retry_failed)
            if processed_ids:
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
            workers = max(1, min(workers, len(batches)))
            checkpoint.open()

            def _process_batch(batch):
                if shutdown_requested.is_set():
                    return 0
                api_res = self.adapt_batch(batch)
                merged  = self.merge_results(batch, api_res)
                # Apenas linhas respondidas pela API entram no checkpoint; as
                # demais permanecem pendentes para --resume/--retry-failed.
                ok_ids = {r["id"] for r in api_res if isinstance(r, dict) and "id" in r}
                checkpoint.append([row for row in merged if row["decision_id"] in ok_ids])
                return len(batch)

            executor = ThreadPoolExecutor(max_workers=workers)
            futures  = {executor.submit(_process_batch, b): b for b in batches}
            try:
                with tqdm(
                    total=len(pending), desc="  Adaptando", unit="linhas",
                    disable=not sys.stdout.isatty(),
                ) as pbar:
                    for future in as_completed(futures):
                        batch = futures[future]
                        try:
                            n = future.result()
                        except Exception as exc:
                            n = len(batch)
                            logger.error("Batch falhou: %s: %s", type(exc).__name__, exc)
                            print(f"\n  [erro] batch falhou: {type(exc).__name__}: {exc}")
                        pbar.update(n)
            except KeyboardInterrupt:
                shutdown_requested.set()
                print("\n⚠  Interrompido pelo usuário — salvando checkpoint...")
            finally:
                executor.shutdown(wait=True, cancel_futures=True)
                checkpoint.close()

        # Reconstrói o CSV na ordem original; a última ocorrência de cada id no
        # checkpoint vence (relevante para linhas reprocessadas via --retry-failed).
        id_to_result = {r.get("decision_id", ""): r for r in checkpoint.load()}
        final_rows: list[dict] = []
        for idx, row in enumerate(all_rows):
            rid = row.get("_id") or self._row_id(row, idx)
            rec = id_to_result.get(rid)
            if rec is not None:
                final_rows.append(rec)
            else:
                clean = {k: v for k, v in row.items() if k != "_id"}
                clean.update(EMPTY_BR_FIELDS)
                clean["stereotype_type_br"] = row.get("stereotype_type", "")
                clean["decision_id"]        = rid
                final_rows.append(clean)

        out_df = pd.DataFrame(final_rows)
        out_df.to_csv(output_path, index=False)

        parquet_path: Path | None = None
        if write_parquet:
            parquet_path = output_path.with_suffix(".parquet")
            try:
                out_df.to_parquet(parquet_path, index=False)
            except (ImportError, ValueError, OSError) as exc:
                logger.warning("Parquet não gerado (%s). Instale pyarrow para habilitar.", exc)
                parquet_path = None

        def _conf(r):
            return safe_float(r.get("confianca_traducao_br"), 0.0)

        alta     = sum(1 for r in final_rows if _conf(r) >= 0.9)
        mod_alta = sum(1 for r in final_rows if 0.7 <= _conf(r) < 0.9)
        moderada = sum(1 for r in final_rows if 0.5 <= _conf(r) < 0.7)
        baixa    = sum(1 for r in final_rows if _conf(r) < 0.5)
        sem_traducao = sum(1 for r in final_rows if not r.get("text_no_marker_br"))

        usage_end = self._usage_snapshot()
        usage = {
            k: usage_end.get(k, 0) - usage_start.get(k, 0)
            for k in ("requests", "input_tokens", "output_tokens")
        }

        print(f"\n  Salvo em: {output_path}"
              + (f"  (+ {parquet_path.name})" if parquet_path else ""))
        print(
            f"  Confianca — alta(>=0.9): {alta} | mod-alta(0.7-0.89): {mod_alta} | "
            f"moderada(0.5-0.69): {moderada} | baixa(<0.5): {baixa}"
        )
        print(
            f"  Batches  — ok: {self.batches_ok} | reparados: {self.batches_repaired} | "
            f"parciais: {self.batches_partial} | falhos: {self.batches_fail}"
        )
        if usage["requests"]:
            print(
                f"  Tokens   — entrada: {usage['input_tokens']} | "
                f"saída: {usage['output_tokens']} | requisições: {usage['requests']}"
            )
        if sem_traducao:
            print(f"  Pendentes: {sem_traducao} linhas sem tradução — reexecute com --retry-failed")

        manifest = {
            "input":          input_path.name,
            "output":         output_path.name,
            "started_at":     started_at.isoformat(timespec="seconds"),
            "finished_at":    datetime.now().isoformat(timespec="seconds"),
            "provider":       self.llm.provider,
            "model":          self.llm.model,
            "prompt_version": PROMPT_VERSION,
            "batch_size":     batch_size,
            "workers":        workers,
            "sample":         sample,
            "resume":         resume,
            "retry_failed":   retry_failed,
            "interrupted":    shutdown_requested.is_set(),
            "rows_total":     total,
            "rows_pending_at_start": len(pending),
            "rows_without_translation": sem_traducao,
            "confidence": {
                "alta": alta, "moderada_alta": mod_alta,
                "moderada": moderada, "baixa": baixa,
            },
            "batches": {
                "ok":       self.batches_ok,
                "repaired": self.batches_repaired,
                "partial":  self.batches_partial,
                "fail":     self.batches_fail,
            },
            "usage": usage,
        }
        manifest_path = output_path.with_name(output_path.stem + ".run.json")
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  Manifesto: {manifest_path}")

        logger.info(
            "Concluído: %s -> %s | alta=%d mod_alta=%d moderada=%d baixa=%d sem_traducao=%d | "
            "batches ok=%d repaired=%d partial=%d fail=%d | tokens in=%d out=%d",
            input_path.name, output_path.name, alta, mod_alta, moderada, baixa, sem_traducao,
            self.batches_ok, self.batches_repaired, self.batches_partial, self.batches_fail,
            usage["input_tokens"], usage["output_tokens"],
        )
        return final_rows

    def _usage_snapshot(self) -> dict:
        snap = getattr(self.llm, "usage_snapshot", None)
        return snap() if callable(snap) else {}

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
            f"**Versão do prompt:** `{PROMPT_VERSION}`  ",
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

        lines += ["## Framework Legal Consultado", ""] + LEGAL_TABLE_MD

        output_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"\n  Decision log salvo em: {output_path}")
