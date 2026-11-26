'''
File:   smoke_llm.py
Brief:  Live smoke check of the configured LLM endpoint (lists models).
Author: Mistress-Lukutar
Date:   2026-11-26
Version: v0.1.0

Reads LLM_* settings from the environment / .env and calls the provider's
model-list endpoint. Exit code 0 = the endpoint answered. Never prints the
API key.

Usage:
    python scripts/smoke_llm.py
'''

from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "src")

from mechanic.config import get_settings  # noqa: E402
from mechanic.llm import (  # noqa: E402
    AiProtocol,
    Endpoint,
    OpenAiClient,
    get_shared_http_client,
)


async def main() -> int:
    '''Fetch and print the model list from the configured endpoint.'''
    settings = get_settings()
    try:
        protocol = AiProtocol(settings.llm_protocol)
    except ValueError:
        print(f"unknown protocol in settings: {settings.llm_protocol}")
        return 2
    endpoint = Endpoint(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model_id=settings.llm_model,
        protocol=protocol,
    )
    http = get_shared_http_client()
    client = OpenAiClient(http)
    try:
        models = await client.fetch_models(endpoint.base_url, endpoint.api_key)
    except Exception as exc:  # noqa: BLE001 - smoke script reports and exits
        print(f"LLM endpoint check FAILED: {exc}")
        return 1
    print(f"LLM endpoint OK: {len(models)} models")
    for model in models[:5]:
        tools = "tools" if model.supports_tools else "no-tools"
        print(f"  - {model.model_id} ({tools})")
    configured = endpoint.model_id
    if configured and all(m.model_id != configured for m in models):
        print(f"WARNING: configured model '{configured}' is not in the list")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
