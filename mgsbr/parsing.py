"""Parsing e normalização das respostas JSON do LLM, e schemas válidos das colunas."""

import json

from json_repair import repair_json

# Modelos menores frequentemente traduzem as chaves para PT-BR; normalizamos aqui.
TYPE_NORM: dict[str, str] = {
    "raça": "race",        "raca": "race",
    "gênero": "gender",    "genero": "gender",
    "profissão": "profession", "profissao": "profession",
    "religião": "religion", "religiao": "religion",
    "região": "regiao",    "orientação sexual": "orientacao_sexual",
    "orientacao sexual": "orientacao_sexual",
}
VALID_TYPES = {"race", "gender", "profession", "religion", "regiao", "orientacao_sexual"}
VALID_LEGAL = {"crime_racismo", "crime_trabalho", "vies_cultural", "neutro"}


def strip_markdown_fences(text: str) -> str:
    """Remove blocos de código markdown que alguns modelos inserem ao redor do JSON."""
    text = text.strip()
    if not text:
        return text

    # remove prefixos ``` (possivelmente aninhados)
    while text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        text = text.strip()

    # remove sufixos ``` (possivelmente aninhados)
    while text.endswith("```"):
        text = text[:-3].strip()

    return text


def normalize_parsed_json(result) -> list[dict] | None:
    """Garante que o JSON retornado pelo LLM seja sempre uma lista de dicts.

    Retorna None se a estrutura for irrecuperável (dispara retry).
    """
    if result is None:
        return None

    # objeto único → wrap em array
    if isinstance(result, dict):
        result = [result]

    if not isinstance(result, list):
        return None

    # filtra strings/None/números: mantém apenas dicts
    cleaned = [item for item in result if isinstance(item, dict)]

    # se o array veio vazio ou perdeu todos os itens, falha
    if not cleaned:
        return None

    return cleaned


def safe_float(value, default: float = 0.0) -> float:
    """Converte valor para float, suportando None, str e tipos não numéricos."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def parse_llm_json(raw: str) -> tuple[list[dict] | None, bool, str]:
    """Faz strip de fences, parse e normalização da resposta do LLM.

    Retorna (lista de objetos ou None, usou_json_repair, mensagem de erro).
    """
    text = strip_markdown_fences(raw)
    try:
        norm = normalize_parsed_json(json.loads(text))
        if norm is not None:
            return norm, False, ""
        err = "JSON tipo inválido (não é array de objetos)"
    except json.JSONDecodeError as exc:
        err = f"JSON inválido: {exc}"

    try:
        norm = normalize_parsed_json(json.loads(repair_json(text)))
        if norm is not None:
            return norm, True, ""
    except Exception:
        pass

    return None, False, err
