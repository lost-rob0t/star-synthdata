#!/usr/bin/env python3
"""Generate StarIntel task data through llm.starintel.actor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import random
import time
import tomllib
import urllib.error
import urllib.request

TASKS = {
    "starintel_prolog": {
        "model": "cheap",
        "system": "Produce compact, executable SWI-Prolog training examples for StarIntel. Return only the requested code.",
        "prompts": [
            "Write a small StarIntel Prolog knowledge base with facts, validation rules, one derived predicate, and plunit tests. Use fictional data only.",
            "Create Prolog rules that validate actor manifests, including accepts, emits, capabilities, and star:// URI constraints. Include positive and negative tests.",
            "Create a Prolog expert-system example for document routing with explicit facts, rules, explanations, and plunit tests.",
        ],
    },
    "starintel_json": {
        "model": "cheap",
        "system": "Generate valid fictional StarIntel JSON/JSON-LD examples. Never use real personal data. Return JSON only.",
        "prompts": [
            "Generate a fictional StarIntel dataset manifest containing document types, provenance, actor routing, retention metadata, and validation fields.",
            "Generate a fictional JSON-LD StarIntel document bundle with person-like placeholders, messages, provenance, and relationships. Use obviously synthetic values.",
            "Generate a StarIntel actor manifest in JSON with accepts, emits, capabilities, rate limits, schemas, and health metadata.",
        ],
    },
    "ingest": {
        "model": "cheap",
        "system": "Write robust ingestion examples using public or synthetic inputs only. Include idempotency, provenance, retries, and tests.",
        "prompts": [
            "Create a StarIntel ingest job that converts a synthetic NDJSON feed into validated documents and records provenance. Return code plus a concise test fixture.",
            "Create an idempotent migration-safe ingest worker for a public RSS-style feed, with backoff, checkpointing, and deterministic document IDs.",
        ],
    },
    "migrations": {
        "model": "cheap",
        "system": "Generate reversible data/schema migrations with tests and rollback notes.",
        "prompts": [
            "Write a StarIntel document migration from an older actor field layout to a versioned capabilities layout. Include up/down logic and fixtures.",
            "Write a CouchDB-oriented StarIntel migration that backfills provenance fields without rewriting unchanged documents. Include validation tests.",
        ],
    },
    "osint_tools": {
        "model": "smart",
        "system": "Design lawful public-source research tools. Use public data only; respect robots, authentication boundaries, privacy, and rate limits. Do not bypass anti-bot controls or access restrictions.",
        "prompts": [
            "Design a StarIntel tool that collects and normalizes public website metadata into provenance-rich documents. Include rate limiting, caching, and tests.",
            "Design a public-record research actor that accepts a domain or organization name and emits sourced documents. Include uncertainty handling and source attribution.",
            "Design an OSINT utility for comparing public URLs, titles, timestamps, and content hashes over time. Include a safe tool schema and unit tests.",
        ],
    },
}

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_documents",
            "description": "Search fictional StarIntel documents in a training sandbox.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_star_uri",
            "description": "Resolve a fictional star:// URI in the training sandbox.",
            "parameters": {
                "type": "object",
                "properties": {"uri": {"type": "string"}},
                "required": ["uri"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_target",
            "description": "Submit a fictional target to a sandbox actor.",
            "parameters": {
                "type": "object",
                "properties": {"actor": {"type": "string"}, "target": {"type": "object"}},
                "required": ["actor", "target"],
            },
        },
    },
]


def post_json(url: str, token: str, payload: dict) -> dict:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "starintel-dataset-factory/1"},
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.load(response)


def assistant_message(response: dict) -> dict:
    return response["choices"][0]["message"]


def record_id(task: str, prompt: str, model: str, ordinal: int) -> str:
    raw = f"{task}\0{prompt}\0{model}\0{ordinal}".encode()
    return hashlib.sha256(raw).hexdigest()[:24]


def synthesize_text(task: str, spec: dict, model: str, endpoint: str, token: str, ordinal: int, rng: random.Random, config: dict) -> dict:
    prompt = rng.choice(spec["prompts"])
    payload = {
        "model": model,
        "messages": [{"role": "system", "content": spec["system"]}, {"role": "user", "content": prompt}],
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
    }
    response = post_json(endpoint, token, payload)
    assistant = assistant_message(response)
    return {
        "id": record_id(task, prompt, model, ordinal),
        "task": f"synthetic_{task}",
        "messages": payload["messages"] + [assistant],
        "source": {"kind": "synthetic_llm", "endpoint": endpoint, "model": response.get("model", model), "created": response.get("created")},
        "tags": ["synthetic", task, "llm.starintel.actor"],
    }


def synthesize_tool_call(model: str, endpoint: str, token: str, ordinal: int, rng: random.Random, config: dict) -> dict:
    prompts = [
        "Find up to 5 fictional documents about Acme Observatory and then resolve star://dataset/demo/acme.",
        "Resolve star://actor/domain-hunt and submit a fictional example.com target to it.",
        "Search the sandbox for fictional documents mentioning Project Lantern with a limit of 3.",
    ]
    prompt = rng.choice(prompts)
    messages = [
        {"role": "system", "content": "Use the provided sandbox tools when needed. All entities are fictional training data."},
        {"role": "user", "content": prompt},
    ]
    payload = {
        "model": model,
        "messages": messages,
        "tools": TOOLS,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": config["max_tokens"],
    }
    response = post_json(endpoint, token, payload)
    assistant = assistant_message(response)
    conversation = messages + [assistant]
    for tool_call in assistant.get("tool_calls", []) or []:
        function = tool_call.get("function", {})
        fake_result = {"ok": True, "tool": function.get("name"), "result": "synthetic sandbox result", "items": []}
        conversation.append({"role": "tool", "tool_call_id": tool_call.get("id", "synthetic"), "content": json.dumps(fake_result, sort_keys=True)})
    return {
        "id": record_id("tool_calling", prompt, model, ordinal),
        "task": "synthetic_tool_calling",
        "messages": conversation,
        "tools": TOOLS,
        "source": {"kind": "synthetic_llm", "endpoint": endpoint, "model": response.get("model", model), "created": response.get("created")},
        "tags": ["synthetic", "tool-calling", "llm.starintel.actor"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="dataset.toml")
    parser.add_argument("--output-dir", default="work/synthetic")
    parser.add_argument("--count", type=int)
    parser.add_argument("--seed", type=int, default=545)
    args = parser.parse_args()

    config = tomllib.loads(pathlib.Path(args.config).read_text())["synthetic"]
    endpoint = os.getenv("STARINTEL_LLM_ENDPOINT", config["endpoint"])
    token = os.getenv("STARINTEL_LLM_TOKEN")
    if not token:
        raise SystemExit("STARINTEL_LLM_TOKEN is required")
    cheap_model = os.getenv("STARINTEL_SYNTH_MODEL") or config["cheap_model"]
    smart_model = os.getenv("STARINTEL_TOOL_MODEL") or config["smart_model"]
    count = args.count or int(config["count_per_task"])
    output_dir = pathlib.Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    for task, spec in TASKS.items():
        model = cheap_model if spec["model"] == "cheap" else smart_model
        path = output_dir / f"{task}.jsonl"
        with path.open("w") as handle:
            for ordinal in range(count):
                for attempt in range(5):
                    try:
                        record = synthesize_text(task, spec, model, endpoint, token, ordinal, rng, config)
                        handle.write(json.dumps(record, sort_keys=True) + "\n")
                        handle.flush()
                        break
                    except (urllib.error.URLError, KeyError, json.JSONDecodeError):
                        if attempt == 4:
                            raise
                        time.sleep(2**attempt)

    path = output_dir / "tool_calling.jsonl"
    with path.open("w") as handle:
        for ordinal in range(count):
            record = synthesize_tool_call(smart_model, endpoint, token, ordinal, rng, config)
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            handle.flush()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
