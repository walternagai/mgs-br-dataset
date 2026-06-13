import json

from mgsbr.checkpoint import Checkpoint


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def test_load_skips_corrupted_lines(tmp_path):
    path = tmp_path / "ck.jsonl"
    path.write_text('{"decision_id": "a"}\nnão é json\n{"decision_id": "b"}\n')
    records = Checkpoint(path).load()
    assert [r["decision_id"] for r in records] == ["a", "b"]


def test_processed_ids_excludes_failed_with_retry_failed(tmp_path):
    path = tmp_path / "ck.jsonl"
    _write_jsonl(path, [
        {"decision_id": "ok1", "text_no_marker_br": "traduzido"},
        {"decision_id": "fail1", "text_no_marker_br": ""},
    ])
    ck = Checkpoint(path)
    assert ck.processed_ids() == {"ok1", "fail1"}
    assert ck.processed_ids(retry_failed=True) == {"ok1"}


def test_archive_renames_existing(tmp_path):
    path = tmp_path / "ck.jsonl"
    _write_jsonl(path, [{"decision_id": "a"}])
    backup = Checkpoint(path).archive()
    assert not path.exists()
    assert backup is not None and backup.exists()
    assert ".bak-" in backup.name


def test_archive_noop_when_missing(tmp_path):
    assert Checkpoint(tmp_path / "nada.jsonl").archive() is None


def test_append_and_load_roundtrip(tmp_path):
    ck = Checkpoint(tmp_path / "ck.jsonl")
    ck.open()
    ck.append([{"decision_id": "a", "text_no_marker_br": "x"}])
    ck.append([])  # não deve quebrar
    ck.close()
    assert len(ck.load()) == 1
