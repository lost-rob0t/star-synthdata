# llm.starintel.actor training contract

`star-synthdata` submits fine-tunes to `POST /v1/training/jobs`. The actor is the control plane: callers do not select or authenticate directly to a GPU vendor.

## Request

The request uses `kind = starintel.fine_tune.v1` and includes:

- immutable `dataset.uri`, `dataset.sha256`, and format
- `base_model`, trainer (`axolotl`) and method (`qlora`)
- a bounded training recipe
- a `compute` policy with `strategy = cheapest_compatible`, GPU VRAM/count constraints, spot preference, and a hard USD budget ceiling
- artifact publication rules and an idempotency key

The actor should return a durable job ID. Replaying the same idempotency key must not rent another GPU.

## Actor state machine

`queued -> pricing -> provisioning -> staging -> training -> validating -> publishing -> succeeded`

Terminal failures are `rejected`, `failed`, `cancelled`, and `budget_exhausted`. Any provisioned instance must be destroyed from every terminal path.

## Provider adapters

Provider selection belongs inside the actor. The first adapters should be Runpod and Vast-compatible compute backends, selected by effective estimated job cost after checking VRAM, CUDA capability, storage, egress, and availability. Credentials remain actor-side.

## Training worker

The worker downloads and SHA-256 verifies the corpus bundle, materializes `dataset/train.jsonl`, runs the checked-in Axolotl QLoRA recipe, evaluates a held-out slice, uploads adapter/checkpoint artifacts, and reports structured metrics to the actor.

The default publish action is the LoRA adapter only. Merging a full model is an explicit later action to avoid unnecessary storage and egress cost.
