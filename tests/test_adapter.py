import json

import pandas as pd

from mgsbr.adapter import DatasetAdapter
from mgsbr.checkpoint import Checkpoint

from .conftest import (
    EchoLLM,
    ScriptedLLM,
    make_input_rows,
    response_for_ids,
    write_input_csv,
)


def make_batch(ids):
    return [
        {
            "_id": i,
            "text_with_marker": f"The ===w=== {i}.",
            "text_no_marker": f"The w {i}.",
            "label": "stereotype",
            "stereotype_type": "race",
        }
        for i in ids
    ]


class TestAdaptBatch:
    def test_success(self):
        llm = EchoLLM()
        adapter = DatasetAdapter(llm)
        result = adapter.adapt_batch(make_batch(["a", "b"]))
        assert {r["id"] for r in result} == {"a", "b"}
        assert adapter.batches_ok == 1
        assert adapter.batches_fail == 0

    def test_partial_response_retries_only_missing_ids(self):
        llm = ScriptedLLM([response_for_ids(["a"]), response_for_ids(["b"])])
        adapter = DatasetAdapter(llm)
        result = adapter.adapt_batch(make_batch(["a", "b"]))
        assert {r["id"] for r in result} == {"a", "b"}
        assert adapter.batches_ok == 1
        # a segunda chamada deve pedir apenas o id faltante
        second_rows = json.loads(llm.calls[1].split("Linhas a adaptar:")[1])
        assert [r["id"] for r in second_rows] == ["b"]

    def test_unknown_ids_discarded(self):
        llm = ScriptedLLM([response_for_ids(["a", "zzz"])])
        adapter = DatasetAdapter(llm)
        result = adapter.adapt_batch(make_batch(["a"]))
        assert [r["id"] for r in result] == ["a"]

    def test_exhausted_retries_counts_failure(self):
        llm = ScriptedLLM(["não é json"] * 3)
        adapter = DatasetAdapter(llm)
        result = adapter.adapt_batch(make_batch(["a", "b"]))
        assert result == []
        assert adapter.batches_fail == 1
        assert adapter.rows_failed == 2

    def test_partial_after_retries_counts_partial(self):
        llm = ScriptedLLM([response_for_ids(["a"]), "x", "x"])
        adapter = DatasetAdapter(llm)
        result = adapter.adapt_batch(make_batch(["a", "b"]))
        assert [r["id"] for r in result] == ["a"]
        assert adapter.batches_partial == 1
        assert adapter.rows_failed == 1

    def test_api_exception_then_success(self):
        llm = ScriptedLLM([RuntimeError("boom"), response_for_ids(["a"])])
        adapter = DatasetAdapter(llm)
        result = adapter.adapt_batch(make_batch(["a"]))
        assert [r["id"] for r in result] == ["a"]
        assert adapter.batches_ok == 1


class TestMergeResults:
    def test_normalizes_type_and_legal(self):
        adapter = DatasetAdapter(EchoLLM())
        batch = make_batch(["a"])
        api = json.loads(response_for_ids(
            ["a"], stereotype_type_br="raça", legal_status_br="unrelated",
            confianca_traducao_br=None,
        ))
        merged = adapter.merge_results(batch, api)
        assert merged[0]["stereotype_type_br"] == "race"
        assert merged[0]["legal_status_br"] == "neutro"
        assert merged[0]["confianca_traducao_br"] == 0.0

    def test_missing_api_result_yields_empty_fields(self):
        adapter = DatasetAdapter(EchoLLM())
        merged = adapter.merge_results(make_batch(["a"]), [])
        assert merged[0]["text_no_marker_br"] == ""
        assert merged[0]["legal_status_br"] == "neutro"
        assert merged[0]["decision_id"] == "a"
        assert adapter.decisions == []


class TestProcessFile:
    def _paths(self, tmp_path):
        input_path = tmp_path / "sample-MGS.csv"
        output_path = tmp_path / "sample-MGS-BR.csv"
        ckpt_dir = tmp_path / "ckpt"
        return input_path, output_path, ckpt_dir

    def test_end_to_end(self, tmp_path):
        input_path, output_path, ckpt_dir = self._paths(tmp_path)
        write_input_csv(input_path, make_input_rows(4))

        adapter = DatasetAdapter(EchoLLM(), checkpoint_dir=ckpt_dir)
        adapter.process_file(
            input_path, output_path,
            batch_size=2, workers=1, write_parquet=False,
        )

        df = pd.read_csv(output_path, dtype=str, keep_default_na=False)
        assert len(df) == 4
        assert (df["text_no_marker_br"] != "").all()
        assert df["decision_id"].nunique() == 4

        manifest = json.loads(
            output_path.with_name("sample-MGS-BR.run.json").read_text(encoding="utf-8")
        )
        assert manifest["rows_total"] == 4
        assert manifest["rows_without_translation"] == 0
        assert manifest["batches"]["ok"] == 2
        assert manifest["model"] == "echo-1"
        assert manifest["prompt_version"]

    def test_failed_rows_stay_pending_and_resume_retries(self, tmp_path):
        input_path, output_path, ckpt_dir = self._paths(tmp_path)
        write_input_csv(input_path, make_input_rows(2))

        # 1ª execução: o modelo só devolve lixo → nada entra no checkpoint
        bad = DatasetAdapter(ScriptedLLM(["lixo"] * 3), checkpoint_dir=ckpt_dir)
        bad.process_file(
            input_path, output_path, batch_size=2, workers=1, write_parquet=False,
        )
        df = pd.read_csv(output_path, dtype=str, keep_default_na=False)
        assert (df["text_no_marker_br"] == "").all()
        ckpt = Checkpoint(ckpt_dir / "sample-MGS_checkpoint.jsonl")
        assert ckpt.load() == []

        # 2ª execução com --resume: as linhas falhas são reprocessadas
        good = DatasetAdapter(EchoLLM(), checkpoint_dir=ckpt_dir)
        good.process_file(
            input_path, output_path,
            resume=True, batch_size=2, workers=1, write_parquet=False,
        )
        df = pd.read_csv(output_path, dtype=str, keep_default_na=False)
        assert (df["text_no_marker_br"] != "").all()

    def test_new_run_archives_stale_checkpoint(self, tmp_path):
        input_path, output_path, ckpt_dir = self._paths(tmp_path)
        write_input_csv(input_path, make_input_rows(2))

        for _ in range(2):
            adapter = DatasetAdapter(EchoLLM(), checkpoint_dir=ckpt_dir)
            adapter.process_file(
                input_path, output_path, batch_size=2, workers=1, write_parquet=False,
            )

        backups = list(ckpt_dir.glob("*.bak-*"))
        assert len(backups) == 1
        # o checkpoint ativo contém apenas a execução atual
        assert len(Checkpoint(ckpt_dir / "sample-MGS_checkpoint.jsonl").load()) == 2

    def test_retry_failed_reprocesses_only_empty_rows(self, tmp_path):
        input_path, output_path, ckpt_dir = self._paths(tmp_path)
        rows = make_input_rows(2)
        write_input_csv(input_path, rows)

        adapter = DatasetAdapter(EchoLLM(), checkpoint_dir=ckpt_dir)
        rid0 = adapter._row_id(rows[0], 0)
        rid1 = adapter._row_id(rows[1], 1)

        # checkpoint pré-existente: linha 0 completa, linha 1 sem tradução
        ckpt_path = ckpt_dir / "sample-MGS_checkpoint.jsonl"
        ckpt_path.parent.mkdir(parents=True)
        with open(ckpt_path, "w", encoding="utf-8") as f:
            f.write(json.dumps({**rows[0], "text_with_marker_br": "ok",
                                "text_no_marker_br": "ok", "stereotype_type_br": "race",
                                "legal_status_br": "neutro", "lei_referencia_br": "neutro",
                                "confianca_traducao_br": 0.9, "decision_id": rid0}) + "\n")
            f.write(json.dumps({**rows[1], "text_with_marker_br": "",
                                "text_no_marker_br": "", "stereotype_type_br": "race",
                                "legal_status_br": "neutro", "lei_referencia_br": "neutro",
                                "confianca_traducao_br": 0.0, "decision_id": rid1}) + "\n")

        llm = adapter.llm
        adapter.process_file(
            input_path, output_path,
            resume=True, retry_failed=True, batch_size=5, workers=1, write_parquet=False,
        )

        # só a linha sem tradução foi reenviada à API
        assert len(llm.calls) == 1
        assert [r["id"] for r in llm.calls[0]] == [rid1]

        df = pd.read_csv(output_path, dtype=str, keep_default_na=False)
        by_id = df.set_index("decision_id")
        assert by_id.loc[rid0, "text_no_marker_br"] == "ok"
        assert by_id.loc[rid1, "text_no_marker_br"] == f"BR {rid1}"

    def test_parquet_written_when_available(self, tmp_path):
        try:
            import pyarrow  # noqa: F401
        except ImportError:
            import pytest
            pytest.skip("pyarrow não instalado")

        input_path, output_path, ckpt_dir = self._paths(tmp_path)
        write_input_csv(input_path, make_input_rows(2))
        adapter = DatasetAdapter(EchoLLM(), checkpoint_dir=ckpt_dir)
        adapter.process_file(input_path, output_path, batch_size=2, workers=1)
        assert output_path.with_suffix(".parquet").exists()
