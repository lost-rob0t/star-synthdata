#!/usr/bin/env python3
"""Record synthetic tool-calling traces from a stronger OpenRouter teacher via curl."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import random
import subprocess
import time
import tomllib

from synthesize_actor import TOOLS

PROMPTS = [
    "Find up to 5 fictional documents about Acme Observatory and then resolve star://dataset/demo/acme.",
    "Resolve star://actor/domain-hunt and submit a fictional example.com target to it.",
    "Search the sandbox for fictional documents mentioning Project Lantern with a limit of 3.",
    "Search for fictional Acme North records, resolve star://dataset/demo/acme-north, then submit a sandbox target if the URI resolves.",
]


def record_id(prompt: str, model: str, ordinal: int) -> str:
    return hashlib.sha256(f"openrouter-tool\0{prompt}\0{model}\0{ordinal}".encode()).hexdigest()[:24]


def curl_chat(endpoint: str, api_key: str, payload: dict) -> dict:
    command = [
        "curl",
        "--fail-with-body",
        "--silent",
        "--show-error",
        "--retry",
        "4",
        "--retry-all-errors",
        "--max-time",
        "180",
        endpoint,
        "-H",
        f"Authorization: Bearer {api_key}",
        "-H",
        "Content-Type: application/json",
        "-d",
        json.dumps(payload),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def make_record(endpoint: str, api_key: str, model: str, prompt: str, ordinal: int, max_tokens: int) -> dict:
    messages = [
        {"role": "system", "content": "Use the provided sandbox tools when needed. All entities and tool results are fictional training data."},
        {"role": "user", "content": prompt},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": max_tokens,
    }
    response = curl_chat(endpoint, api_key, payload)
    assistant = response["choices"][0]["message"]
    conversation = messages + [assistant]
    for tool_call in assistant.get("tool_calls", []) or []:
        function = tool_call.get("function", {})
        result = {
            "ok": True,
            "tool": function.get("name"),
            "result": "synthetic sandbox result",
            "items": [],
        }
        conversation.append(
            {
                "role": "tool",
                "tool_call_id": tool_call.get("id", "synthetic"),
                "content": json.dumps(result, sort_keys=True),
            }
        )
    return {
        "id": record_id(prompt, model, ordinal),
        "task": "synthetic_tool_calling",
        "messages": conversation,
        "tools": TOOLS,
        "source": {
            "kind": "synthetic_openrouter_curl",
            "endpoint": endpoint,
            "model": response.get("model", model),
            "response_id": response.get("id"),
            "usage": response.get("usage"),
        },
        "tags": ["synthetic", "tool-calling", "openrouter", "curl", "teacher"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="dataset.toml")
    parser.add_argument("--output", default="work/synthetic/tool_calling.jsonl")
    parser.add_argument("--count", type=int)
    parser.add_argument("--seed", type=int, default=545)
    args = parser.parse_args()

    config = tomllib.loads(pathlib.Path(args.config).read_text())["synthetic"]
    endpoint = os.getenv("OPENROUTER_ENDPOINT") or config["openrouter_endpoint"]
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("OPENROUTER_TOOL_MODEL") or config.get("openrouter_tool_model")
    if not api_key:
        raise SystemExit("OPENROUTER_API_KEY is required")
    if not model:
        raise SystemExit("OPENROUTER_TOOL_MODEL is required; choose the smarter teacher model explicitly")

    count = args.count or int(config["count_per_task"])
    rng = random.Random(args.seed)
    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w") as handle:
        for ordinal in range(count):
            prompt = rng.choice(PROMPTS)
            for attempt in range(5):
                try:
                    row = make_record(endpoint, api_key, model, prompt, ordinal, int(config["max_tokens"]))
                    handle.write(json.dumps(row, sort_keys=True) + "\n")
                    handle.flush()
                    break
                except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError):
                    if attempt == 4:
                        raise
                    time.sleep(2**attempt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
