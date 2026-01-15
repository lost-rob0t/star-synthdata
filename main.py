#!/usr/bin/env python3
"""Synthetic data generator for StarIntel documents."""

import sys
import json
import argparse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "spec" / "starintel_doc"))

from starintel_doc.entities import new_person
from starintel_doc.social_media import new_message, new_social_media_post
from generators import get_generator, GENERATORS


def generate_documents(doc_type: str, count: int, dataset: str, model: str, base_url: str):
    """Generate documents and output as NDJSON to stdout."""
    generator = get_generator(doc_type, model=model, base_url=base_url)

    try:
        for _ in range(count):
            try:
                # Generate raw data using Ollama
                raw_data = generator.generate()

                # Create proper StarIntel document
                if doc_type == "person":
                    doc = new_person(
                        dataset=dataset,
                        fname=raw_data.get("fname", ""),
                        lname=raw_data.get("lname", ""),
                        etype=raw_data.get("etype", "person"),
                        mname=raw_data.get("mname", ""),
                        gender=raw_data.get("gender", ""),
                        bio=raw_data.get("bio", ""),
                        dob=raw_data.get("dob", ""),
                        race=raw_data.get("race", "")
                    )
                elif doc_type == "socialmediapost":
                    doc = new_social_media_post(
                        dataset=dataset,
                        content=raw_data.get("content", ""),
                        user=raw_data.get("user", ""),
                        media=raw_data.get("media", []),
                        replyCount=raw_data.get("replyCount", 0),
                        repostCount=raw_data.get("repostCount", 0),
                        url=raw_data.get("url", ""),
                        links=raw_data.get("links", []),
                        tags=raw_data.get("tags", []),
                        title=raw_data.get("title", ""),
                        group=raw_data.get("group", ""),
                        replyTo=raw_data.get("replyTo", "")
                    )
                elif doc_type == "message":
                    doc = new_message(
                        dataset=dataset,
                        content=raw_data.get("content", ""),
                        platform=raw_data.get("platform", ""),
                        user=raw_data.get("user", ""),
                        isReply=raw_data.get("isReply", False),
                        media=raw_data.get("media", []),
                        messageId=raw_data.get("messageId", ""),
                        replyTo=raw_data.get("replyTo", ""),
                        group=raw_data.get("group", ""),
                        channel=raw_data.get("channel", ""),
                        mentions=raw_data.get("mentions", [])
                    )
                else:
                    print(f"Error: Unknown document type {doc_type}", file=sys.stderr)
                    continue

                # Output as NDJSON
                print(doc.to_json())

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
