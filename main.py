#!/usr/bin/env python3
"""Synthetic data generator for StarIntel documents."""

import sys
import json
import argparse
from uuid import uuid4
from starintel_canonical import SPEC_VERSION, generated, load_schema, validate_document

from generators import get_generator, GENERATORS


def generate_documents(doc_type: str, count: int, dataset: str, model: str, base_url: str):
    """Generate documents and output as NDJSON to stdout."""
    if not 1 <= count <= 2000:
        raise ValueError("count must be in 1..2000")
    schema = load_schema()
    generator = get_generator(doc_type, model=model, base_url=base_url)

    try:
        for _ in range(count):
            try:
                # Generate raw data using Ollama
                raw_data = generator.generate()

                # Preserve raw model output without confusing historical fields with
                # the canonical generated contract. No guessed references are emitted.
                dtype = {"socialmediapost": "social-media-post"}.get(doc_type, doc_type)
                definition = {"person": generated.Person, "message": generated.Message,
                              "socialmediapost": generated.SocialMediaPost}[doc_type]
                fields = {"person": {k: raw_data[k] for k in ("fname", "lname", "bio", "dob") if raw_data.get(k)},
                          "message": {"message": raw_data.get("content", ""), "platform": raw_data.get("platform", "fictional-board")},
                          "socialmediapost": {"content": raw_data.get("content", "")}}[doc_type]
                doc = definition(id="synthetic:"+str(uuid4()), dataset=dataset, dtype=dtype,
                                 schemaVersion=SPEC_VERSION, labels=["synthetic", "ollama-unverified"],
                                 extensions={"org.starintel.synthdata": {"synthetic": True, "rawModelOutput": raw_data}},
                                 **fields)
                validate_document(doc, schema)
                print(json.dumps(doc, ensure_ascii=False))

            except Exception as e:
                print(f"Error generating document: {e}", file=sys.stderr)
                raise

    finally:
        generator.close()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("world", "validate", "import-fixture"):
        from star_synthdata.cli import main as world_main
        return world_main(argv)
    parser = argparse.ArgumentParser(
        description="Generate synthetic StarIntel documents using Ollama"
    )
    parser.add_argument(
        "doc_type",
        choices=list(GENERATORS.keys()),
        help="Type of document to generate"
    )
    parser.add_argument(
        "-n", "--count",
        type=int,
        default=10,
        help="Number of documents to generate (default: 10)"
    )
    parser.add_argument(
        "-d", "--dataset",
        default="synthdata",
        help="Dataset name (default: synthdata)"
    )
    parser.add_argument(
        "-m", "--model",
        default="llama3.2",
        help="Ollama model to use (default: llama3.2)"
    )
    parser.add_argument(
        "-u", "--url",
        default="http://localhost:11434",
        help="Ollama base URL (default: http://localhost:11434)"
    )

    args = parser.parse_args(argv)

    generate_documents(
        doc_type=args.doc_type,
        count=args.count,
        dataset=args.dataset,
        model=args.model,
        base_url=args.url
    )


if __name__ == "__main__":
    main()
