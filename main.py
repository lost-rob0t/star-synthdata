#!/usr/bin/env python3
"""Synthetic data generator for StarIntel documents."""

import sys
import json
import argparse
from uuid import uuid4
from starintel_canonical import validate_document
from generators import get_generator, GENERATORS


def build_document(doc_type: str, raw_data: dict, dataset: str) -> dict:
    """Project generated values, preserving non-contract metadata explicitly."""
    dtype = {"socialmediapost": "socialmpost"}.get(doc_type, doc_type)
    if dtype not in {"person", "socialmpost", "message"}:
        raise ValueError(f"Unsupported generator: {doc_type}")
    from starintel_canonical import load_schema, DOCUMENT_TYPES
    fields = load_schema()["$defs"][DOCUMENT_TYPES[dtype]]["properties"]
    doc = {"id": f"synthetic:{uuid4()}", "dataset": dataset,
           "dtype": dtype, "schemaVersion": "0.10.1",
           "collector": "star-synthdata", "labels": ["synthetic"],
           "extensions": {"star_synthdata": {"synthetic": True}}}
    extra = {}
    for key, value in raw_data.items():
        if key == "dtype":
            continue
        target = "message" if dtype == "message" and key == "content" else key
        # Generated handles, media URLs and reply IDs are not proven StarReferences.
        if target in {"user", "media", "replyTo", "mentions"}:
            extra[key] = value
        elif target in fields and target not in doc:
            if target in {"dob", "url"} and value == "":
                continue
            doc[target] = value
        else:
            extra[key] = value
    if extra:
        doc["extensions"]["star_synthdata"]["generatedMetadata"] = extra
    validate_document(doc)
    return doc


def generate_documents(doc_type: str, count: int, dataset: str, model: str, base_url: str):
    """Generate documents and output as NDJSON to stdout."""
    generator = get_generator(doc_type, model=model, base_url=base_url)

    try:
        for _ in range(count):
            try:
                # Generate raw data using Ollama
                raw_data = generator.generate()

                doc = build_document(doc_type, raw_data, dataset)
                print(json.dumps(doc, ensure_ascii=False, allow_nan=False))

            except Exception as e:
                print(f"Error generating document: {e}", file=sys.stderr)
                continue

    finally:
        generator.close()


def main():
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

    args = parser.parse_args()

    generate_documents(
        doc_type=args.doc_type,
        count=args.count,
        dataset=args.dataset,
        model=args.model,
        base_url=args.url
    )


if __name__ == "__main__":
    main()
