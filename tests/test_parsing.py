from mgsbr.parsing import (
    normalize_parsed_json,
    parse_llm_json,
    safe_float,
    strip_markdown_fences,
)


class TestStripMarkdownFences:
    def test_plain_text_unchanged(self):
        assert strip_markdown_fences('[{"a": 1}]') == '[{"a": 1}]'

    def test_json_fence(self):
        assert strip_markdown_fences('```json\n[{"a": 1}]\n```') == '[{"a": 1}]'

    def test_nested_fences(self):
        assert strip_markdown_fences('```\n```json\n[1]\n```\n```') == "[1]"

    def test_empty(self):
        assert strip_markdown_fences("") == ""
        assert strip_markdown_fences("   ") == ""


class TestNormalizeParsedJson:
    def test_list_of_dicts_passthrough(self):
        assert normalize_parsed_json([{"a": 1}]) == [{"a": 1}]

    def test_single_dict_wrapped(self):
        assert normalize_parsed_json({"a": 1}) == [{"a": 1}]

    def test_non_dict_items_filtered(self):
        assert normalize_parsed_json([{"a": 1}, "x", None, 3]) == [{"a": 1}]

    def test_irrecoverable_types(self):
        assert normalize_parsed_json(None) is None
        assert normalize_parsed_json("texto") is None
        assert normalize_parsed_json(42) is None
        assert normalize_parsed_json([]) is None
        assert normalize_parsed_json(["a", "b"]) is None


class TestSafeFloat:
    def test_values(self):
        assert safe_float(None) == 0.0
        assert safe_float("0.8") == 0.8
        assert safe_float(0.5) == 0.5
        assert safe_float("abc") == 0.0
        assert safe_float("", default=1.0) == 1.0


class TestParseLlmJson:
    def test_valid_array(self):
        parsed, repaired, err = parse_llm_json('[{"id": "a"}]')
        assert parsed == [{"id": "a"}]
        assert repaired is False
        assert err == ""

    def test_fenced_array(self):
        parsed, repaired, _ = parse_llm_json('```json\n[{"id": "a"}]\n```')
        assert parsed == [{"id": "a"}]
        assert repaired is False

    def test_broken_json_repaired(self):
        parsed, repaired, _ = parse_llm_json('[{"id": "a",}]')
        assert parsed == [{"id": "a"}]
        assert repaired is True

    def test_garbage_returns_none(self):
        parsed, repaired, err = parse_llm_json("isto não é json")
        assert parsed is None
        assert err != ""
