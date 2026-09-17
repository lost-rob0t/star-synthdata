#!/usr/bin/env python3
"""Turn harvested public code and synthetic shards into deterministic chat JSONL."""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import pathlib
import random
import tomllib
from collections import defaultdict


def stable_id(*parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()
    return digest[:24]


def excluded(path: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def language_for(path: pathlib.Path, languages: dict[str, list[str]]) -> str | None:
    suffix = path.suffix.lower()
    for language, suffixes in languages.items():
        if suffix in suffixes:
            return language
    return None


def path_task(path: str, language: str) -> str:
    lower = path.lower()
    if language == "prolog":
        return "public_prolog"
    if any(token in lower for token in ("migration", "migrate", "schema")):
        return "public_migration"
    if any(token in lower for token in ("ingest", "import", "etl", "scrape", "collector")):
        return "public_ingest"
    if any(token in lower for token in ("tool", "actor", "mcp")):
        return "public_tooling"
    return "public_code"


def chunk_text(text: str, chunk_chars: int, min_chars: int) -> list[str]:
    chunks: list[str] = []
    cursor = 0
    while cursor < len(text):
        end = min(len(text), cursor + chunk_chars)
        if end < len(text):
            newline = text.rfind("\n", cursor + min_chars, end)
            if newline > cursor:
                end = newline + 1
        chunk = text[cursor:end]
        if len(chunk.strip()) >= min_chars:
            chunks.append(chunk)
        cursor = max(end, cursor + 1)
    return chunks


def completion_record(repo: dict, relpath: str, language: str, chunk: str, index: int) -> dict | None:
    split = max(64, int(len(chunk) * 0.72))
    newline = chunk.rfind("\n", 0, split)
    if newline > 64:
        split = newline + 1
    prefix = chunk[:split].rstrip()
    suffix = chunk[split:].lstrip()
    if len(prefix) < 64 or len(suffix) < 32:
        return None
    task = path_task(relpath, language)
    prompt = (
        f"Continue this {language} source file faithfully. Return only the missing continuation.\n\n"
        f"Repository: {repo['full_name']}\nPath: {relpath}\n\n{prefix}"
    )
    return {
        "id": stable_id(repo["full_name"], relpath, str(index), task),
        "task": task,
        "messages": [
            {"role": "system", "content": "You are a precise StarIntel software engineering model."},
            {"role": "user", "content": prompt},
            {"role": "assistant", "content": suffix},
        ],
        "source": {
            "kind": "public_github",
            "repository": repo["full_name"],
            "path": relpath,
            "license": repo.get("license"),
            "url": repo.get("html_url"),
        },
        "tags": [language, task, "public-code"],
    }


def iter_public_records(config: dict, repositories: list[dict]):
    corpus = config["corpus"]
    max_bytes = int(corpus["max_file_bytes"])
    chunk_chars = int(corpus["chunk_chars"])
    min_chars = int(corpus["min_chunk_chars"])
    patterns = list(corpus.get("exclude_globs", []))
    languages = corpus["languages"]

    for repo in repositories:
        if not repo.get("ok"):
            continue
        root = pathlib.Path(repo["target"])
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            relpath = path.relative_to(root).as_posix()
            if excluded(relpath, patterns):
                continue
            language = language_for(path, languages)
            if not language:
                continue
            try:
                if path.stat().st_size > max_bytes:
                    continue
                text = path.read_text(errors="strict")
            except (OSError, UnicodeError):
                continue
            for index, chunk in enumerate(chunk_text(text, chunk_chars, min_chars)):
                record = completion_record(repo, relpath, language, chunk, index)
                if record:
                    yield record


def load_jsonl(path: pathlib.Path):
    if not path.exists():
        return
    with path.open() as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_jsonl(path: pathlib.Path, records) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True) + "\n")
            count += 1
    return count


def weighted_mix(groups: dict[str, list[dict]], weights: dict[str, float], seed: int) -> list[dict]:
    rng = random.Random(seed)
    nonempty = {name: rows for name, rows in groups.items() if rows and weights.get(name, 0) > 0}
    if not nonempty:
        return []
    target = max(len(rows) / weights[name] for name, rows in nonempty.items())
    mixed: list[dict] = []
    for name, rows in nonempty.items():
        desired = max(1, round(target * weights[name]))
        if desired <= len(rows):
            mixed.extend(rng.sample(rows, desired))
        else:
            mixed.extend(rows)
            mixed.extend(rng.choice(rows) for _ in range(desired - len(rows)))
    rng.shuffle(mixed)
    return mixed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="dataset.toml")
    parser.add_argument("--repos", default="work/repositories.json")
    parser.add_argument("--synthetic-dir", default="work/synthetic")
    parser.add_argument("--output-dir", default="work/dataset")
    parser.add_argument("--seed", type=int, default=545)
    args = parser.parse_args()

    config = tomllib.loads(pathlib.Path(args.config).read_text())
    repositories = json.loads(pathlib.Path(args.repos).read_text())
    output_dir = pathlib.Path(args.output_dir)

    public = list(iter_public_records(config, repositories))
    write_jsonl(output_dir / "public.jsonl", public)

    groups: dict[str, list[dict]] = defaultdict(list)
    for row in public:
        key = "public_prolog" if row["task"] == "public_prolog" else "public_code"
        groups[key].append(row)

    synth_dir = pathlib.Path(args.synthetic_dir)
    mapping = {
        "synthetic_starintel_prolog": "starintel_prolog.jsonl",
        "synthetic_starintel_json": "starintel_json.jsonl",
        "synthetic_tool_calling": "tool_calling.jsonl",
        "synthetic_ingest": "ingest.jsonl",
        "synthetic_migrations": "migrations.jsonl",
        "synthetic_osint_tools": "osint_tools.jsonl",
    }
    for group, filename in mapping.items():
        groups[group].extend(load_jsonl(synth_dir / filename) or [])

    weights = {name: float(value) for name, value in config["mix"].items()}
    mixed = weighted_mix(groups, weights, args.seed)
    count = write_jsonl(output_dir / "train.jsonl", mixed)

    manifest = {
        "format": "openai_messages_jsonl",
        "records": count,
        "seed": args.seed,
        "weights": weights,
        "groups": {name: len(rows) for name, rows in sorted(groups.items())},
        "sha256": hashlib.sha256((output_dir / "train.jsonl").read_bytes()).hexdigest(),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
