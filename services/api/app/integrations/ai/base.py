from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class AIRequest:
    task: str  # e.g. "nl_to_plan"
    system: str
    user: str
    json_schema: dict | None = None
    context: dict = field(default_factory=dict)  # structured context for deterministic providers
    max_output_tokens: int = 1200


@dataclass
class AIResponse:
    content: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0


class AIProvider(ABC):
    name: str

    @abstractmethod
    def complete(self, req: AIRequest) -> AIResponse: ...
