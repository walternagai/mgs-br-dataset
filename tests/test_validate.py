import pandas as pd

from mgsbr.validate import main, marker_pairs, validate_file

BASE_ROW = {
    "text_with_marker": "The ===dirty=== people.",
    "text_no_marker": "The dirty people.",
    "label": "stereotype",
    "stereotype_type": "race",
    "text_with_marker_br": "O povo ===sujo===.",
    "text_no_marker_br": "O povo sujo.",
    "stereotype_type_br": "race",
    "legal_status_br": "crime_racismo",
    "lei_referencia_br": "Lei 7.716/1989 Art. 20",
    "confianca_traducao_br": "0.9",
    "decision_id": "000000_aaaaaa",
}


def make_row(**overrides):
    row = dict(BASE_ROW)
    row.update(overrides)
    return row


def write_pair(tmp_path, rows, name="good"):
    """Grava o CSV adaptado e o original correspondente com a mesma contagem."""
    br_path = tmp_path / f"{name}-MGS-BR.csv"
    pd.DataFrame(rows).to_csv(br_path, index=False)
    orig_cols = ["text_with_marker", "text_no_marker", "label", "stereotype_type"]
    pd.DataFrame(rows)[orig_cols].to_csv(tmp_path / f"{name}-MGS.csv", index=False)
    return br_path


def test_marker_pairs():
    assert marker_pairs("a ===b=== c") == 1
    assert marker_pairs("===a=== e ===b===") == 2
    assert marker_pairs("sem marcador") == 0


def test_valid_file_passes(tmp_path):
    rows = [
        make_row(decision_id="000000_aaaaaa"),
        make_row(
            decision_id="000001_bbbbbb",
            stereotype_type="gender", stereotype_type_br="gender",
            legal_status_br="neutro", lei_referencia_br="neutro",
        ),
    ]
    path = write_pair(tmp_path, rows)
    report = validate_file(path)
    assert report["errors"] == []
    assert report["warnings"] == []
    assert report["stats"]["rows"] == 2


def test_errors_detected(tmp_path):
    rows = [
        # decision_id duplicado + tipo inválido (não normalizado)
        make_row(decision_id="dup", stereotype_type_br="raça"),
        # legal_status fora do schema
        make_row(decision_id="dup", legal_status_br="unrelated"),
    ]
    path = write_pair(tmp_path, rows, name="bad")
    report = validate_file(path)
    msgs = " | ".join(report["errors"])
    assert "duplicados" in msgs
    assert "stereotype_type_br" in msgs
    assert "legal_status_br" in msgs


def test_warnings_detected(tmp_path):
    rows = [
        # marcadores perdidos na tradução
        make_row(decision_id="000000_aaaaaa", text_with_marker_br="O povo sujo."),
        # crime com referência legal truncada
        make_row(decision_id="000001_bbbbbb", lei_referencia_br="Lei"),
        # label unrelated classificado como crime
        make_row(decision_id="000002_cccccc", label="unrelated"),
        # linha sem tradução
        make_row(
            decision_id="000003_dddddd",
            stereotype_type="gender", stereotype_type_br="gender",
            legal_status_br="neutro", lei_referencia_br="neutro",
            text_with_marker_br="", text_no_marker_br="",
            confianca_traducao_br="0.0",
        ),
    ]
    path = write_pair(tmp_path, rows, name="warn")
    report = validate_file(path)
    assert report["errors"] == []
    msgs = " | ".join(report["warnings"])
    assert "marcadores" in msgs
    assert "inespecífica" in msgs
    assert "unrelated" in msgs
    assert "sem tradução" in msgs


def test_row_count_mismatch_warns(tmp_path):
    br_path = tmp_path / "cut-MGS-BR.csv"
    pd.DataFrame([make_row()]).to_csv(br_path, index=False)
    pd.DataFrame([make_row(), make_row()]).to_csv(tmp_path / "cut-MGS.csv", index=False)
    report = validate_file(br_path)
    assert any("Linhas:" in w for w in report["warnings"])


def test_missing_columns_is_error(tmp_path):
    path = tmp_path / "x-MGS-BR.csv"
    pd.DataFrame([{"text_no_marker": "a"}]).to_csv(path, index=False)
    report = validate_file(path)
    assert any("Colunas ausentes" in e for e in report["errors"])


def test_main_exit_codes(tmp_path):
    good = write_pair(tmp_path, [make_row()], name="ok")
    assert main([str(good)]) == 0

    bad = write_pair(tmp_path, [make_row(legal_status_br="xxx")], name="ko")
    assert main([str(bad)]) == 1


def test_main_strict_promotes_warnings(tmp_path):
    rows = [make_row(
        stereotype_type="gender", stereotype_type_br="gender",
        legal_status_br="neutro", lei_referencia_br="neutro",
        text_with_marker_br="", text_no_marker_br="", confianca_traducao_br="0.0",
    )]
    path = write_pair(tmp_path, rows, name="strict")
    assert main([str(path)]) == 0
    assert main([str(path), "--strict"]) == 1


def test_main_json_report(tmp_path):
    good = write_pair(tmp_path, [make_row()], name="rep")
    out = tmp_path / "report.json"
    assert main([str(good), "--json", str(out)]) == 0
    assert out.exists()
