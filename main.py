#!/usr/bin/env python3
"""Synthetic data generator for StarIntel documents."""

import sys
import argparse
from uuid import uuid4
from copy import deepcopy
from jsonschema import Draft202012Validator
from starintel_canonical import Document, DOCUMENT_TYPES, SPEC_VERSION, FORMAT_CHECKER, load_schema
from generators import get_generator, GENERATORS


def canonical_document(doc_type, raw_data, dataset):
    """Project declared fields and retain the complete synthetic input."""
    dtype = {"socialmediapost": "socialmpost"}.get(doc_type, doc_type)
    schema = load_schema()
    definition = schema["$defs"][DOCUMENT_TYPES[dtype]]
    fields = {}
    retained = []
    for name, value in raw_data.items():
        key = "message" if dtype == "message" and name == "content" else name
        if key in {"id", "dataset", "dtype", "schemaVersion", "extensions"}:
            continue
        node = definition["properties"].get(key)
        if node is not None and Draft202012Validator({**node, "$defs": schema["$defs"]}, format_checker=FORMAT_CHECKER).is_valid(value):
            fields[key] = deepcopy(value)
        else:
            retained.append(name)
    fields.update(id="synth:" + str(uuid4()), dataset=dataset, dtype=dtype, schemaVersion=SPEC_VERSION,
                  extensions={"starintel.synthdata": {"input": deepcopy(raw_data), "unprojectedFields": retained}})
    return Document.from_dict(fields).to_dict()


def generate_documents(doc_type: str, count: int, dataset: str, model: str, base_url: str):
    """Generate and validate canonical documents before writing NDJSON."""
    generator = get_generator(doc_type, model=model, base_url=base_url)
    failures = 0
    try:
        for _ in range(count):
            try:
                raw_data = generator.generate()
                document = canonical_document(doc_type, raw_data, dataset)
                print(Document.from_dict(document).to_json())
            except Exception as error:
                failures += 1
                print(f"Error generating document: {error}", file=sys.stderr)
    finally:
        generator.close()
    return failures


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

    failures = generate_documents(
        doc_type=args.doc_type,
        count=args.count,
        dataset=args.dataset,
        model=args.model,
        base_url=args.url
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
