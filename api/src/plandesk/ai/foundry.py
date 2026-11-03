"""Microsoft Foundry provider: a project's OpenAI-compatible client with structured output.

Authentication is Entra ID only (DefaultAzureCredential: managed identity in
Azure, the developer's az login locally). No API keys.
"""

from __future__ import annotations

import json

from azure.ai.projects.aio import AIProjectClient
from azure.identity.aio import DefaultAzureCredential
from openai import AsyncOpenAI

from plandesk.ai.prompt import OUTPUT_SCHEMA, SYSTEM_PROMPT, user_message
from plandesk.ai.provider import PROMPT_VERSION, ProviderResult
from plandesk.services.adaptation import AdaptationInput


class FoundryProvider:
    name = "foundry"

    def __init__(self, endpoint: str, deployment: str) -> None:
        if not endpoint or not deployment:
            raise ValueError(
                "foundry provider needs FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL_DEPLOYMENT"
            )
        self._deployment = deployment
        self._credential = DefaultAzureCredential()
        self._project = AIProjectClient(endpoint=endpoint, credential=self._credential)
        self._client: AsyncOpenAI = self._project.get_openai_client()

    async def propose(self, inp: AdaptationInput) -> ProviderResult:
        completion = await self._client.chat.completions.create(
            model=self._deployment,
            temperature=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_message(inp)},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "adaptations", "strict": True, "schema": OUTPUT_SCHEMA},
            },
        )
        content = completion.choices[0].message.content or "{}"
        try:
            raw = json.loads(content)
        except json.JSONDecodeError:
            raw = {"suggestions": "unparseable"}
        return ProviderResult(
            raw=raw, model_deployment=self._deployment, prompt_version=PROMPT_VERSION
        )

    async def aclose(self) -> None:
        await self._client.close()
        await self._project.close()
        await self._credential.close()
