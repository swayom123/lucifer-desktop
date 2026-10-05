"""Provider-neutral model contract."""

from typing import Protocol

from pydantic import BaseModel, Field


class ModelRequest(BaseModel):
    model_class: str
    messages: list[dict[str, str]]
    max_output_tokens: int = Field(gt=0)


class ModelResponse(BaseModel):
    content: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None


class ModelProvider(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
