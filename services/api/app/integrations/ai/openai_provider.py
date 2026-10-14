import time

from app.core.config import get_settings
from app.integrations.ai.base import AIProvider, AIRequest, AIResponse


class OpenAIProvider(AIProvider):
    name = "openai"

    def __init__(self):
        from openai import OpenAI
        s = get_settings()
        self.model = s.openai_model
        self.client = OpenAI(api_key=s.openai_api_key, timeout=s.ai_timeout_seconds, max_retries=0)

    def complete(self, req: AIRequest) -> AIResponse:
        start = time.perf_counter()
        kwargs = {}
        if req.json_schema:
            kwargs["response_format"] = {"type": "json_schema",
                                         "json_schema": {"name": req.task, "schema": req.json_schema, "strict": True}}
        r = self.client.chat.completions.create(
            model=self.model, temperature=0, max_tokens=req.max_output_tokens,
            messages=[{"role": "system", "content": req.system}, {"role": "user", "content": req.user}], **kwargs)
        usage = r.usage
        return AIResponse(content=r.choices[0].message.content or "", provider=self.name, model=r.model,
                          input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                          output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                          latency_ms=int((time.perf_counter() - start) * 1000))
