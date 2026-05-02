"""
llm/adapter.py

Thin, swappable adapter for your corporate LLM.
The rest of the system calls CorporateLLMAdapter.query() — internals
can be swapped (Azure OpenAI, AWS Bedrock, internal API) without
touching any other module.
"""
from __future__ import annotations

import structlog
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config.settings import settings
from llm.prompts import SYSTEM_PROMPT, build_user_message

log = structlog.get_logger()


class CorporateLLMAdapter:
    """
    Calls your internal LLM endpoint using the OpenAI chat completions format.
    Most enterprise LLMs (Azure OpenAI, private deployments) use this format.

    If your corp LLM uses a different schema, override _build_payload()
    and _parse_response() only.
    """

    def __init__(self):
        self.endpoint    = settings.corp_llm_endpoint
        self.model       = settings.corp_llm_model_name
        self.max_tokens  = settings.corp_llm_max_tokens
        self.temperature = settings.corp_llm_temperature
        self.timeout     = settings.corp_llm_timeout_seconds
        self.headers = {
            "Content-Type":  "application/json",
            "Authorization": f"Bearer {settings.corp_llm_api_key}",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
    def query(self, user_query: str, context: str,
              conversation_history: list[dict] | None = None) -> str:
        """
        Send query + context to the corporate LLM and return the response text.

        Args:
            user_query:           The user's natural language question
            context:              Pre-assembled graph + vector context
            conversation_history: Optional list of prior {role, content} turns
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        # Inject prior conversation turns (for multi-turn chat)
        if conversation_history:
            messages.extend(conversation_history)

        # Final user message with context
        messages.append({
            "role":    "user",
            "content": build_user_message(context, user_query),
        })

        payload = self._build_payload(messages)

        log.info("llm_request", model=self.model, query_len=len(user_query),
                 context_len=len(context))

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(self.endpoint, json=payload, headers=self.headers)
            response.raise_for_status()

        result = self._parse_response(response.json())
        log.info("llm_response", response_len=len(result))
        return result

    def _build_payload(self, messages: list[dict]) -> dict:
        """Override this if your corp LLM uses a non-OpenAI payload schema."""
        return {
            "model":       self.model,
            "messages":    messages,
            "max_tokens":  self.max_tokens,
            "temperature": self.temperature,
        }

    def _parse_response(self, data: dict) -> str:
        """Override this if your corp LLM returns a non-OpenAI response schema."""
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as e:
            log.error("llm_parse_error", data=str(data)[:200])
            raise ValueError(f"Unexpected LLM response format: {e}") from e
