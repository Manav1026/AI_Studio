import json
import time

import httpx

from app.core.config import get_settings
from app.integrations.ai.base import AIProvider, AIRequest, AIResponse


class AnthropicProvider(AIProvider):
    """Second provider behind the same gateway interface (plain HTTPS, no SDK lock-in)."""
    name = "anthropic"

    def __init__(self):
        s = get_settings()
        self.model = s.anthropic_model
        self.key = s.anthropic_api_key
        self.http = httpx.Client(timeout=s.ai_timeout_seconds)

    def complete(self, req: AIRequest) -> AIResponse:
        start = time.perf_counter()
        system = req.system
        if req.json_schema:
            system += "\nJSON schema:\n" + json.dumps(req.json_schema)
        r = self.http.post("https://api.anthropic.com/v1/messages", headers={
            "x-api-key": self.key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": self.model, "max_tokens": req.max_output_tokens, "temperature": 0, "system": system,
                  "messages": [{"role": "user", "content": req.user}]})
        r.raise_for_status()
        body = r.json()
        text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
        usage = body.get("usage", {})
        return AIResponse(content=text, provider=self.name, model=body.get("model", self.model),
                          input_tokens=usage.get("input_tokens", 0), output_tokens=usage.get("output_tokens", 0),
                          latency_ms=int((time.perf_counter() - start) * 1000))
