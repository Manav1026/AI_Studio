"""AI Gateway: the only place that knows about AI vendors. Handles provider selection, retries,
token/cost accounting and tracing. Domain code depends on this, never on a provider SDK."""
import json
import re
import time
from decimal import Decimal

from app.core.config import get_settings
from app.core.errors import UpstreamError
from app.core.logging import get_logger
from app.core.telemetry import tracer
from app.integrations.ai.base import AIProvider, AIRequest, AIResponse

log = get_logger("ai_gateway")

# USD per 1M tokens (input, output). Keep in config/DB in production.
PRICES = {
    "mock-planner-v1": (0.0, 0.0),
    "gpt-4o-mini": (0.15, 0.60), "gpt-4o": (2.50, 10.0), "gpt-4.1-mini": (0.40, 1.60),
    "claude-sonnet-4-5": (3.0, 15.0), "claude-haiku-4-5": (1.0, 5.0),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    key = next((k for k in PRICES if model.startswith(k)), None)
    pin, pout = PRICES.get(key, (0.0, 0.0))
    return Decimal(str(round((input_tokens * pin + output_tokens * pout) / 1_000_000, 6)))


def _build_provider(name: str) -> AIProvider:
    if name == "openai":
        from app.integrations.ai.openai_provider import OpenAIProvider
        return OpenAIProvider()
    if name == "anthropic":
        from app.integrations.ai.anthropic_provider import AnthropicProvider
        return AnthropicProvider()
    from app.integrations.ai.mock_provider import MockAIProvider
    return MockAIProvider()


class AIGateway:
    def __init__(self, provider: AIProvider | None = None):
        s = get_settings()
        self.provider = provider or _build_provider(s.ai_provider)
        self.max_retries = s.ai_max_retries

    def complete(self, req: AIRequest) -> AIResponse:
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            with tracer.start_as_current_span("ai.complete") as span:
                span.set_attribute("ai.provider", self.provider.name)
                span.set_attribute("ai.task", req.task)
                try:
                    resp = self.provider.complete(req)
                    span.set_attribute("ai.input_tokens", resp.input_tokens)
                    span.set_attribute("ai.output_tokens", resp.output_tokens)
                    log.info("ai_completion", provider=resp.provider, model=resp.model, task=req.task,
                             input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
                             latency_ms=resp.latency_ms)
                    return resp
                except Exception as exc:  # provider errors are normalised here
                    last_exc = exc
                    log.warning("ai_completion_failed", provider=self.provider.name, attempt=attempt,
                                error=type(exc).__name__)
                    time.sleep(min(0.5 * 2 ** attempt, 4))
        raise UpstreamError("AI provider unavailable", details={"provider": self.provider.name,
                                                                "error": type(last_exc).__name__})

    @staticmethod
    def parse_json(content: str) -> dict:
        text = content.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
        if fence:
            text = fence.group(1)
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("AI response did not contain a JSON object")
        return json.loads(text[start: end + 1])
