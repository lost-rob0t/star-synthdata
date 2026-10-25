# StarIntel Synthetic Data Generator

An offline, seeded fictional world generator and the original explicit Ollama
person/message/post commands. Output uses the **StarLang-generated StarIntel
0.10.1** Python SDK, pinned to commit
`6aa8051dc7ea560943a60a25e1d600467f2778bc`. There are no handwritten document
classes or copied schema fragments. Each output record passes the SDK's concrete
document validator, including its semantic checks.

## Install and run

```sh
python -m venv .venv
. .venv/bin/activate
pip install '.[test]'
synthdata world --size 60 --seed 42 --preview
synthdata world --size 60 --seed 42 --output /tmp/fictional-world
synthdata validate /tmp/fictional-world
synthdata import-fixture /tmp/fictional-world /tmp/fictional-world.sqlite
pytest -q
```

`nix develop`, `nix build`, and `nix flake check` are also supported. The installed
Nix executable is `./result/bin/synthdata`. `python main.py world ...` remains a
source-tree entry point. GitHub Actions runs Python 3.10/3.12 installed-wheel
tests and the full Nix package check on the PR's exact head commit.

No server, model, credentials, or network is needed for world generation after
installation. No upload or live ingestion command exists. Output directories and
SQLite databases must be **new**; existing paths are refused. `--preview` (alias
`--dry-run`) constructs and validates the graph and prints metrics without writing.

## World configuration

| Option | Default | Meaning |
| --- | --- | --- |
| `--size` | 60 | Persons, 1–2000; total records are larger |
| `--seed` | 42 | Signed 64-bit seed |
| `--communities` | 3 | 1–min(persons, KB places); use 1 for a single person |
| `--start`, `--end` | 2025-01-01, 2025-12-31 | UTC dates; end exclusive; 1–3660 days within 1900–2100 |
| `--scenario` | archipelago | `archipelago`, `trade`, `campus`, or a custom KB scenario |
| `--topology` | preferential | `preferential`, `local`, `uniform` |
| `--missingness` | 0 | Probability of omitting a relation record from observations |
| `--noise` | 0 | Uniform additive relation-weight noise, clipped to [0,1] |
| `--dataset` | synthetic-world | Must match `synthetic-[a-z0-9-]{1,60}` |
| `--kb` | packaged KB | Alternate version-1 JSON knowledge base |

Examples:

```sh
synthdata world --size 500 --communities 6 --seed 197 --scenario trade --output /tmp/trade
synthdata world --size 80 --scenario campus --topology local --missingness .2 --noise .1 --output /tmp/campus
synthdata validate /tmp/campus --observations
synthdata import-fixture /tmp/campus /tmp/campus.sqlite --observations
```

The Python API is `generate(Config(...), load_kb(optional_path))` from
`star_synthdata.world` and `star_synthdata.kb`; it returns a `World` containing
`documents`, `observations`, `artifacts`, `manifest`, and `kb`. `export(world,
new_directory)` writes the bundle.

## Fictional knowledge base and extension

[`star_synthdata/data/world.json`](star_synthdata/data/world.json) defines six
invented settlements, household-size distributions, eight industry archetypes,
24 role templates, services, topic vocabularies, four event archetypes, three
scenarios, and eleven typed relation rules. Personal names are combinatorial,
with an explicit synthetic ordinal to avoid mistaken identity and label clashes.
No personal source data is fetched. Coordinates illustrate an invented ocean
archipelago and must not be treated as real street addresses.

Copy this JSON and pass `--kb your-world.json`. Add sectors with `name`, `suffix`,
`roles`, `service`, and `topics`; places with names and decimal-string coordinates;
event templates with `kind`, `title`, and `action`; scenarios with locality [0,1],
events per person [0,2], and integer ties per person [0,10]. Relation patterns list
canonical source/destination types and a `local` constraint. Keep the required
patterns when extending the KB. Unsupported document types are rejected. New
relation production rules require extending `Builder.build`, not just adding a
name. The KB is declarative data in the existing Python architecture; no separate
Lisp/Prolog engine is introduced. It can be translated into facts by future
consumers without changing the canonical documents.

Households use `org` with `organizationType=household`; roles use person occupation
and a namespaced extension; minutes use `file` with actual UTF-8 bytes and SHA-256.
Locations use `location` and `geo-point`, accounts use `user`, and infrastructure
uses `domain`, `host`, `service`. Canonical refs carry the target dtype and ID.
Model metadata is under `extensions["org.starintel.synthdata"]` and provenance.
Hosts use documentation IPv6 `2001:db8::/32`; contact URLs use `.example.invalid`.
No phone numbers, email targets, real identities or scraped profiles are emitted.

## Graph mechanisms and limits

Persons are distributed round-robin across communities and assigned household
sizes from the KB. Adults work at local employers in allowed roles. Employer
selection favors earlier local organizations as hubs. The social graph grows in
person order, choosing prior persons without replacement. Preferential mode
weights choices by degree+1 and usually chooses local candidates. Local mode
chooses local candidates when available; uniform mode ignores community and
degree. Initial people necessarily create some cross-community bridges.

Events are sampled within the window and processed chronologically. Local
participants and organizers create attendance records; meeting minutes and
messages appear after the event. New collaborations begin only after a shared
event and cite it as evidence. All reference targets exist before or at the
referring record's timestamp. Birth dates precede adult employment. There are
no simulated deaths, relocations, employment changes, dissolution, or edge decay
in model v1. Longitudinal evolution consists of events and newly formed
collaborations; this is not a full demographic simulator.

Weights are decimal strings in [0,1], representing simulated tie strength, not
confidence in a real claim. This is an **uncalibrated model**: locality, degree
bias, and event rates are useful testing mechanisms, not measured social laws.
Small graphs have finite-size effects. Scenario names do not imply empirical
realism. No sensitive attributes are inferred or modeled.

IDs are UUID5-derived from the model version, canonical KB, full truth config,
dtype and logical key. Same seed/config/KB/model yields identical JSON bytes,
including IDs and time fields, independent of wall clock or output path.
Changing truth parameters creates a new namespace. Changing observation rates
does not change truth IDs. Version upgrades may change results and must bump
`MODEL_VERSION` when generation semantics change.

Observations retain entities, intrinsic references, and artifacts; missingness
samples **relation records only**. It is not entity-redaction or a missing-at-random
claim about real evidence. Noise changes only observed relation weights. Truth
and observation JSONL files are separate snapshots with the same document IDs;
do not concatenate or import both into one fixture store.

## Artifacts and validation

Each bundle contains `truth.jsonl`, `observations.jsonl`, `kb.json`, a checksum
`manifest.json`, `graph.dot`, and actual `artifacts/minutes-*.txt` files. The
manifest records config, model/schema/KB identity, counts by dtype and predicate,
local-edge fraction, maximum and mean social degree, and file checksums.
`dot -Tsvg graph.dot -o graph.svg` renders the graph if Graphviz is installed.
The checked-in [`examples/small-world`](examples/small-world) is a reproducible
6-person campus fixture (seed 7); tests regenerate and compare it.

`validate` checks canonical schema, typed references, synthetic namespace,
validity intervals, adulthood, allowed roles, community constraints, event
causality, duplicate IDs/edges, file contents/hashes and bundle checksums.
`import-fixture` validates before creating a SQLite database, inserts actual
persisted records and foreign-key references transactionally, closes/reopens
it, and checks full readback equality and graph invariants. This is a real SQLite
fixture-store integration test, **not acceptance by the StarIntel Lisp server**.
This repository had no server import seam; server/transport code is unchanged.
Production server ingestion remains outside this PR.

Tests include corruption and invalid-input cases, no-network generation, same
and different seeds, three topology comparisons across multiple seeds,
observation sampling, small and 500-person scenarios, installed CLI/package data,
canonical output from mocked Ollama responses, and SQLite readback. Hosted
Actions uploads test results, wheel and generated evidence.

## Existing Ollama mode

```sh
ollama serve
ollama pull llama3.2
synthdata person -n 5
synthdata message -n 20 -d synthdata -m llama3.2
synthdata socialmediapost -n 10
```

These explicit commands still contact the configured Ollama endpoint (`-u`),
keep `-n/-d/-m/-u`, and use the existing generator registry in `generators.py`.
Output is now flat, schema-validated 0.10.1. Raw parsed model input lives in a
namespaced extension; historical fields are not copied into illegal canonical
fields or invented references. Invalid model output fails the command rather
than returning a misleading successful partial run. Ollama mode is unseeded,
unverified, and does not provide world-mode coherence or contact-safety guarantees.
Use offline world mode for reproducible, bounded fixtures.
