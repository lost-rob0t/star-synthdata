#!/usr/bin/env python3
"""Discover and clone public repositories into a reproducible corpus workspace."""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request


def request_json(url: str, token: str | None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "starintel-dataset-factory/1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def list_public_repos(owner: str, token: str | None) -> list[dict]:
    repos: list[dict] = []
    page = 1
    while True:
        url = f"https://api.github.com/users/{owner}/repos?type=public&sort=full_name&per_page=100&page={page}"
        batch = request_json(url, token)
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            break
        page += 1
    return repos


def clone_repo(repo: dict, root: pathlib.Path) -> dict:
    full_name = str(repo["full_name"])
    target = root / full_name.replace("/", "__")
    command = [
        "git",
        "clone",
        "--quiet",
        "--depth=1",
        "--filter=blob:none",
        "--no-tags",
        str(repo["clone_url"]),
        str(target),
    ]
    started = time.time()
    result = subprocess.run(command, text=True, capture_output=True)
    return {
        "full_name": full_name,
        "html_url": repo.get("html_url"),
        "clone_url": repo.get("clone_url"),
        "default_branch": repo.get("default_branch"),
        "fork": bool(repo.get("fork")),
        "archived": bool(repo.get("archived")),
        "license": (repo.get("license") or {}).get("spdx_id"),
        "target": str(target),
        "ok": result.returncode == 0,
        "stderr": result.stderr.strip()[-2000:],
        "elapsed_s": round(time.time() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="dataset.toml")
    parser.add_argument("--output", default="work/repos")
    parser.add_argument("--manifest", default="work/repositories.json")
    args = parser.parse_args()

    config = tomllib.loads(pathlib.Path(args.config).read_text())
    corpus = config["corpus"]
    include_forks = bool(corpus.get("include_forks", False))
    token = os.getenv("GITHUB_TOKEN")

    output = pathlib.Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []

    for owner in corpus["owners"]:
        try:
            repos = list_public_repos(owner, token)
        except urllib.error.HTTPError as exc:
            print(f"github discovery failed for {owner}: {exc}", file=sys.stderr)
            return 2
        for repo in repos:
            if repo.get("private"):
                continue
            if repo.get("fork") and not include_forks:
                continue
            records.append(clone_repo(repo, output))

    manifest = pathlib.Path(args.manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n")

    failed = [record for record in records if not record["ok"]]
    print(json.dumps({"repositories": len(records), "failed": len(failed)}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
