"""Checkpoint JSONL incremental, um por arquivo de entrada.

Regras de integridade:
- Apenas linhas efetivamente respondidas pela API são gravadas (o adapter filtra),
  portanto linhas de lotes falhos permanecem pendentes para --resume.
- Execução sem --resume arquiva o checkpoint anterior em vez de misturá-lo
  silenciosamente à nova execução.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

from .runtime import logger


class Checkpoint:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._handle = None

    def exists(self) -> bool:
        return self.path.exists()

    def archive(self) -> Path | None:
        """Renomeia o checkpoint atual para *.bak-<timestamp> (nova execução sem --resume)."""
        if not self.path.exists():
            return None
        backup = self.path.with_suffix(
            self.path.suffix + f".bak-{datetime.now():%Y%m%d_%H%M%S}"
        )
        self.path.rename(backup)
        logger.info("Checkpoint anterior arquivado em %s", backup)
        print(f"  Checkpoint anterior arquivado: {backup.name}")
        return backup

    def load(self) -> list[dict]:
        records: list[dict] = []
        if not self.path.exists():
            return records
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Linha corrompida ignorada no checkpoint %s", self.path)
        return records

    @staticmethod
    def is_complete(record: dict) -> bool:
        """Linha com tradução não vazia conta como processada com sucesso."""
        return bool(record.get("text_no_marker_br"))

    def processed_ids(self, retry_failed: bool = False) -> set[str]:
        """IDs já processados; com retry_failed, linhas sem tradução voltam à fila."""
        ids: set[str] = set()
        for rec in self.load():
            if retry_failed and not self.is_complete(rec):
                continue
            rid = rec.get("decision_id", "")
            if rid:
                ids.add(rid)
        return ids

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = open(self.path, "a", encoding="utf-8")

    def append(self, rows: list[dict]) -> None:
        if not rows:
            return
        with self._lock:
            for row in rows:
                self._handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
