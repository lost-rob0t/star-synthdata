#!/usr/bin/env python3
"""Submit a corpus fine-tune job to llm.starintel.actor."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import tomllib
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="dataset.toml")
    parser.add_argument("--dataset-uri", required=True)
    parser.add_argument("--manifest", default="work/dataset/manifest.json")
    parser.add_argument("--base-model")
    parser.add_argument("--budget", type=float)
    parser.add_argument("--output", default="work/training-job.json")
    args = parser.parse_args()

    config = tomllib.loads(pathlib.Path(args.config).read_text())["training"]
    manifest = json.loads(pathlib.Path(args.manifest).read_text())
    endpoint = os.getenv("STARINTEL_TRAINING_ENDPOINT", config["endpoint"])
    token = os.getenv("STARINTEL_LLM_TOKEN")
    if not token:
        raise SystemExit("STARINTEL_LLM_TOKEN is required")

    base_model = args.base_model or os.getenv("STARINTEL_BASE_MODEL", config["base_model"])
    budget = args.budget if args.budget is not None else float(config["max_budget_usd"])
    idempotency_key = hashlib.sha256(f"{base_model}\0{args.dataset_uri}\0{manifest['sha256']}".encode()).hexdigest()

    payload = {
        "kind": "starintel.fine_tune.v1",
        "base_model": base_model,
        "dataset": {"uri": args.dataset_uri, "sha256": manifest["sha256"], "format": manifest["format"]},
        "trainer": config["trainer"],
        "method": config["method"],
        "recipe": {
            "max_seq_len": config["max_seq_len"],
            "micro_batch_size": config["micro_batch_size"],
            "gradient_accumulation_steps": config["gradient_accumulation_steps"],
            "num_epochs": config["num_epochs"],
            "learning_rate": config["learning_rate"],
            "load_in_4bit": True,
            "adapter": "qlora",
            "dataset_type": "chat_template",
        },
        "compute": {
            "strategy": config["compute_strategy"],
            "providers": ["runpod", "vast"],
            "gpu_min_vram_gb": config["gpu_min_vram_gb"],
            "gpu_max_count": config["gpu_max_count"],
            "spot": bool(config["spot"]),
            "max_budget_usd": budget,
        },
        "artifacts": {"publish_adapter": True, "publish_merged_model": False, "register_model_alias": "starintel/code-ft"},
        "idempotency_key": idempotency_key,
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
            "User-Agent": "starintel-dataset-factory/1",
        },
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        result = json.load(response)

    output = pathlib.Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
