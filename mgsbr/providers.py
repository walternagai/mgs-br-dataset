"""Presets de provedores e cliente LLM unificado (Anthropic SDK / OpenAI-compatible).

O cliente trata erros transitórios (429, 5xx, timeout) com backoff exponencial +
jitter — separado do retry de parsing JSON feito pelo adapter — e acumula uso de
tokens para estimativa de custo.
"""

import os
import random
import sys
import threading

from .runtime import interruptible_sleep, logger

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

RATE_LIMIT_MAX_RETRIES = 8
RATE_LIMIT_BASE_DELAY = 2.0   # segundos
RATE_LIMIT_MAX_DELAY = 60.0   # segundos

# Nomes cobrem as exceções equivalentes dos SDKs anthropic e openai sem exigir
# que ambos estejam instalados.
_RETRYABLE_EXC_NAMES = {
    "RateLimitError",
    "APIConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "ServiceUnavailableError",
}


def _is_retryable(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status == 429 or (isinstance(status, int) and status >= 500):
        return True
    return type(exc).__name__ in _RETRYABLE_EXC_NAMES


def _retry_after_seconds(exc: Exception) -> float | None:
    """Extrai o header retry-after da resposta HTTP, se o SDK o expuser."""
    headers = getattr(getattr(exc, "response", None), "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("retry-after")
        return min(float(value), RATE_LIMIT_MAX_DELAY) if value else None
    except (TypeError, ValueError):
        return None


class LLMClient:
    """Wrapper unificado sobre Anthropic SDK e qualquer endpoint OpenAI-compatible."""

    def __init__(self, provider: str, model: str, api_key: str, base_url: str | None):
        self.provider = provider
        self.model    = model
        preset        = PROVIDERS.get(provider, PROVIDERS["custom"])

        self._usage_lock = threading.Lock()
        self._usage = {"requests": 0, "input_tokens": 0, "output_tokens": 0}

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

    def usage_snapshot(self) -> dict:
        with self._usage_lock:
            return dict(self._usage)

    def _track_usage(self, input_tokens, output_tokens) -> None:
        with self._usage_lock:
            self._usage["requests"] += 1
            self._usage["input_tokens"] += int(input_tokens or 0)
            self._usage["output_tokens"] += int(output_tokens or 0)

    def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
            try:
                if self._backend == "anthropic":
                    return self._call_anthropic(system, user, max_tokens)
                return self._call_openai(system, user, max_tokens)
            except Exception as exc:
                if attempt >= RATE_LIMIT_MAX_RETRIES or not _is_retryable(exc):
                    raise
                wait = _retry_after_seconds(exc)
                if wait is None:
                    wait = min(RATE_LIMIT_BASE_DELAY * (2 ** attempt), RATE_LIMIT_MAX_DELAY)
                    wait += random.uniform(0, wait * 0.25)
                logger.warning(
                    "Erro transitório do provedor (%s) — aguardando %.1fs (tentativa %d/%d)",
                    type(exc).__name__, wait, attempt + 1, RATE_LIMIT_MAX_RETRIES,
                )
                if interruptible_sleep(wait):
                    raise RuntimeError("Shutdown solicitado durante espera de rate limit") from exc
        raise RuntimeError("unreachable")  # pragma: no cover

    def _call_anthropic(self, system: str, user: str, max_tokens: int) -> str:
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        usage = getattr(msg, "usage", None)
        self._track_usage(
            getattr(usage, "input_tokens", 0), getattr(usage, "output_tokens", 0)
        )
        if not msg.content:
            raise RuntimeError(f"Modelo {self.model} retornou conteúdo vazio")
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
        usage = getattr(resp, "usage", None)
        self._track_usage(
            getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0)
        )
        content = resp.choices[0].message.content
        if content is None:
            raise RuntimeError(f"Modelo {self.model} retornou conteúdo vazio")
        return content


def resolve_llm(
    provider: str,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> LLMClient:
    preset = PROVIDERS.get(provider)
    if preset is None:
        sys.exit(f"Provedor desconhecido: '{provider}'. Opções: {', '.join(PROVIDERS)}")

    base_url = base_url or preset["base_url"]
    if provider == "custom" and not base_url:
        sys.exit("Erro: --base-url é obrigatório para --provider custom")

    model = model or preset["default_model"]
    if not api_key and preset["env_key"]:
        api_key = os.environ.get(preset["env_key"], "")
    if not api_key and preset["requires_key"]:
        env_var = preset["env_key"] or "API_KEY"
        sys.exit(
            f"Erro: chave de API não encontrada para '{provider}'.\n"
            f"  Defina {env_var} ou use --api-key <chave>."
        )

    return LLMClient(provider=provider, model=model, api_key=api_key, base_url=base_url)
