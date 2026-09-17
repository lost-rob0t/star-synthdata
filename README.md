# StarIntel Dataset Factory

Build a reproducible fine-tuning corpus from StarIntel public code plus actor-generated synthetic tasks, then submit an 8B QLoRA job to `llm.starintel.actor`.

## Corpus

The dataset factory harvests public repositories owned by `lost-rob0t` and `starintel-labs`, records repository/path/license provenance, chunks supported source files, and converts them into deterministic code-continuation tasks. Prolog is kept as its own task family.

Synthetic shards are generated through the OpenAI-compatible `https://llm.starintel.actor/v1/chat/completions` endpoint:

- StarIntel Prolog facts, rules, validation, and tests
- StarIntel JSON/JSON-LD documents and actor manifests
- simulated tool-calling conversations
- ingest jobs
- reversible migrations
- public-source OSINT tool designs with rate-limit/privacy constraints

`dataset.toml` defines the target mix. `scripts/build_training_mix.py` emits OpenAI-messages JSONL plus an immutable SHA-256 manifest.

## GitHub Actions

`dataset-factory.yml` runs manually or weekly. It harvests public repositories, optionally creates synthetic shards with `STARINTEL_LLM_TOKEN`, builds the weighted mix, and uploads a compressed Actions artifact. With the S3-compatible dataset secrets/variables configured it also publishes the bundle to object storage for training.

Required secret for actor synthesis/training:

```text
STARINTEL_LLM_TOKEN
```

Optional S3-compatible settings:

```text
DATASET_S3_ACCESS_KEY       secret
DATASET_S3_SECRET_KEY       secret
DATASET_S3_ENDPOINT         variable
DATASET_S3_BUCKET           variable
DATASET_S3_REGION           variable
```

Optional model/teacher settings:

```text
STARINTEL_SYNTH_MODEL       default: starintel/synth-cheap
STARINTEL_TOOL_MODEL        default: starintel/synth-smart
OPENROUTER_API_KEY          secret; enables direct curl tool-call recording
OPENROUTER_TOOL_MODEL       variable; explicit stronger teacher model
```

Bulk JSON/Prolog/ingest/migration synthesis uses `llm.starintel.actor`. OSINT-tool synthesis uses the actor smart alias. Tool-calling has an actor fallback, but when `OPENROUTER_API_KEY` and `OPENROUTER_TOOL_MODEL` are set the workflow overwrites that shard with direct OpenRouter traces recorded via `curl`, preserving the teacher response metadata.

## Fine-tuning

`fine-tune.yml` accepts a corpus URI and submits it to:

```text
POST https://llm.starintel.actor/v1/training/jobs
```

The request asks the actor for `cheapest_compatible` compute, a single GPU with at least 24 GiB VRAM, spot capacity when allowed, and a hard dollar budget. The default recipe is Axolotl QLoRA for `Qwen/Qwen3-8B`, 4-bit loading, 8k context, and OpenAI-style chat data. The full actor contract is in `docs/training-contract.md`.

Run locally:

```bash
python scripts/harvest_public_repos.py
STARINTEL_LLM_TOKEN=... python scripts/synthesize_actor.py --count 100
OPENROUTER_API_KEY=... OPENROUTER_TOOL_MODEL=... \
  python scripts/record_openrouter_tools.py --count 100
python scripts/build_training_mix.py
python scripts/submit_finetune.py \
  --dataset-uri s3://starintel-datasets/example.tar.zst \
  --budget 40
```

## Legacy synthetic documents

The original `main.py`/`generators.py` Ollama document generator remains available for Person, SocialMediaPost, and Message NDJSON generation.
