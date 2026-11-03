"""The AI provider seam: one call, retrieved facts in, raw structured JSON out."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from plandesk.services.adaptation import AdaptationInput

PROMPT_VERSION = "adapt-v1"


@dataclass(frozen=True, slots=True)
class ProviderResult:
    raw: Any
    model_deployment: str
    prompt_version: str


class AdaptationProvider(Protocol):
    name: str

    async def propose(self, inp: AdaptationInput) -> ProviderResult: ...
