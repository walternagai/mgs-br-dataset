import json

import pandas as pd
import pytest

import mgsbr.adapter as adapter_mod
from mgsbr.runtime import shutdown_requested

INPUT_COLS = ["text_with_marker", "text_no_marker", "label", "stereotype_type"]


def response_for_ids(ids, **overrides):
    """JSON de resposta válido do LLM para os ids dados."""
    objs = []
    for i in ids:
        obj = {
            "id": i,
            "text_with_marker_br": f"BR ===x=== {i}",
            "text_no_marker_br": f"BR {i}",
            "stereotype_type_br": "race",
            "legal_status_br": "vies_cultural",
            "lei_referencia_br": "Lei 7.716/1989 Art. 20",
            "confianca_traducao_br": 0.9,
            "decision_class": "manutencao",
            "decision_justificativa": "teste",
        }
        obj.update(overrides)
        objs.append(obj)
    return json.dumps(objs, ensure_ascii=False)


class EchoLLM:
    """Responde corretamente a qualquer lote, ecoando os ids pedidos no prompt."""

    provider = "fake"
    model = "echo-1"

    def __init__(self):
        self.calls: list[list[dict]] = []

    def complete(self, system, user, max_tokens=4096):
        rows = json.loads(user.split("Linhas a adaptar:")[1])
        self.calls.append(rows)
        return response_for_ids([r["id"] for r in rows])

    def usage_snapshot(self):
        return {"requests": len(self.calls), "input_tokens": 10, "output_tokens": 20}


class ScriptedLLM:
    """Devolve respostas pré-definidas na ordem; Exceptions na lista são levantadas."""

    provider = "fake"
    model = "scripted-1"

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[str] = []

    def complete(self, system, user, max_tokens=4096):
        self.calls.append(user)
        if not self.responses:
            raise AssertionError("ScriptedLLM sem respostas restantes")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp

    def usage_snapshot(self):
        return {"requests": len(self.calls), "input_tokens": 0, "output_tokens": 0}


def make_input_rows(n):
    return [
        {
            "text_with_marker": f"The ===word{i}=== sentence {i}.",
            "text_no_marker": f"The word{i} sentence {i}.",
            "label": "stereotype",
            "stereotype_type": "race",
        }
        for i in range(n)
    ]


def write_input_csv(path, rows):
    pd.DataFrame(rows, columns=INPUT_COLS).to_csv(path, index=False)


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    monkeypatch.setattr(adapter_mod, "RETRY_DELAY", 0)


@pytest.fixture(autouse=True)
def clean_shutdown_flag():
    shutdown_requested.clear()
    yield
    shutdown_requested.clear()
