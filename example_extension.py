#!/usr/bin/env python3
"""Example of how to extend the generator with a new document type.

This file demonstrates adding a new document type to the synthetic data generator.
Copy this pattern to add your own document types.
"""

from typing import Dict, Any
import json
from generators import OllamaGenerator, GENERATORS


class WebPageGenerator(OllamaGenerator):
    """Generate synthetic WebPage documents.

    This is an example generator. To use it:
    1. Import it in main.py
    2. Add it to GENERATORS dict in generators.py
    3. Add the creation logic in main.py generate_documents()
    """

    def get_prompt(self) -> str:
        return """Generate a realistic web page metadata with the following fields in JSON format:
{
  "url": "full URL",
  "title": "page title",
  "content": "page content or description (100-300 chars)",
  "keywords": ["list", "of", "keywords"],
  "links": ["list of outbound URLs"],
  "headers": {"header-name": "header-value"},
  "statusCode": 200,
  "contentType": "text/html",
  "lastModified": "ISO 8601 timestamp"
}

Generate a diverse, realistic web page. Return ONLY the JSON object, no additional text."""

    def parse_response(self, response: str) -> Dict[str, Any]:
        data = json.loads(response)
        return {
            "dtype": "webpage",
            "url": data.get("url", ""),
            "title": data.get("title", ""),
            "content": data.get("content", ""),
            "keywords": data.get("keywords", []),
            "links": data.get("links", []),
            "headers": data.get("headers", {}),
            "statusCode": data.get("statusCode", 200),
            "contentType": data.get("contentType", "text/html"),
            "lastModified": data.get("lastModified", "")
        }


# Example of another generator for Email documents
class EmailGenerator(OllamaGenerator):
    """Generate synthetic Email documents."""

    def get_prompt(self) -> str:
        return """Generate a realistic email with the following fields in JSON format:
{
  "from": "sender email address",
  "to": ["list", "of", "recipients"],
  "cc": ["cc recipients"],
  "subject": "email subject",
  "body": "email body content",
  "headers": {"header-name": "value"},
  "attachments": ["list of attachment names"],
  "timestamp": "ISO 8601 timestamp",
  "isRead": boolean,
  "labels": ["inbox", "important"]
}

Generate a diverse, realistic email. Return ONLY the JSON object, no additional text."""

    def parse_response(self, response: str) -> Dict[str, Any]:
        data = json.loads(response)
        return {
            "dtype": "email",
            "from": data.get("from", ""),
            "to": data.get("to", []),
            "cc": data.get("cc", []),
            "subject": data.get("subject", ""),
            "body": data.get("body", ""),
            "headers": data.get("headers", {}),
            "attachments": data.get("attachments", []),
            "timestamp": data.get("timestamp", ""),
            "isRead": data.get("isRead", False),
            "labels": data.get("labels", [])
        }


# To activate these generators:
# 1. Add to GENERATORS dict in generators.py:
#    GENERATORS = {
#        ...existing...,
#        "webpage": WebPageGenerator,
#        "email": EmailGenerator,
#    }
#
# 2. Add creation logic in main.py generate_documents():
#    elif doc_type == "webpage":
#        doc = new_webpage(
#            dataset=dataset,
#            url=raw_data.get("url", ""),
#            title=raw_data.get("title", ""),
#            ...
#        )
#
# 3. Use it:
#    python main.py webpage -n 10
