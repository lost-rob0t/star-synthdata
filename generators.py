#!/usr/bin/env python3
"""Generator classes for synthetic StarIntel documents using Ollama."""

import json
import httpx
from typing import Any, Dict
from abc import ABC, abstractmethod


class OllamaGenerator(ABC):
    """Base class for Ollama-based document generators."""

    def __init__(self, model: str = "llama3.2", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.client = httpx.Client(timeout=60.0)

    @abstractmethod
    def get_prompt(self) -> str:
        """Return the prompt for generating this document type."""
        pass

    @abstractmethod
    def parse_response(self, response: str) -> Dict[str, Any]:
        """Parse the LLM response into document fields."""
        pass

    def generate(self) -> Dict[str, Any]:
        """Generate a single document."""
        prompt = self.get_prompt()

        response = self.client.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "format": "json"
            }
        )
        response.raise_for_status()

        result = response.json()
        llm_output = result["response"]

        return self.parse_response(llm_output)

    def close(self):
        """Close the HTTP client."""
        self.client.close()


class PersonGenerator(OllamaGenerator):
    """Generate synthetic Person documents."""

    def get_prompt(self) -> str:
        return """Generate a realistic person profile with the following fields in JSON format:
{
  "fname": "first name",
  "lname": "last name",
  "mname": "middle name (can be empty)",
  "gender": "gender",
  "bio": "brief biography (2-3 sentences)",
  "dob": "date of birth in YYYY-MM-DD format",
  "race": "ethnicity/race",
  "etype": "person"
}

Generate a diverse, realistic person. Return ONLY the JSON object, no additional text."""

    def parse_response(self, response: str) -> Dict[str, Any]:
        data = json.loads(response)
        return {
            "dtype": "person",
            "fname": data.get("fname", ""),
            "lname": data.get("lname", ""),
            "mname": data.get("mname", ""),
            "gender": data.get("gender", ""),
            "bio": data.get("bio", ""),
            "dob": data.get("dob", ""),
            "race": data.get("race", ""),
            "etype": data.get("etype", "person")
        }


class SocialMediaPostGenerator(OllamaGenerator):
    """Generate synthetic SocialMediaPost documents."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.platforms = ["twitter", "mastodon", "bluesky", "threads"]
        self.topics = ["technology", "politics", "entertainment", "sports", "science", "art"]

    def get_prompt(self) -> str:
        return """Generate a realistic social media post with the following fields in JSON format:
{
  "content": "post content (50-280 characters)",
  "user": "username",
  "media": ["list of media URLs if any"],
  "replyCount": number,
  "repostCount": number,
  "url": "post URL",
  "links": ["list of URLs mentioned in post"],
  "tags": ["list of hashtags without # symbol"],
  "title": "post title if applicable",
  "group": "group/community name if applicable"
}

Generate a diverse, realistic social media post. Return ONLY the JSON object, no additional text."""

    def parse_response(self, response: str) -> Dict[str, Any]:
        data = json.loads(response)
        return {
            "dtype": "socialmediapost",
            "content": data.get("content", ""),
            "user": data.get("user", ""),
            "media": data.get("media", []),
            "replyCount": data.get("replyCount", 0),
            "repostCount": data.get("repostCount", 0),
            "url": data.get("url", ""),
            "links": data.get("links", []),
            "tags": data.get("tags", []),
            "title": data.get("title", ""),
            "group": data.get("group", ""),
            "replyTo": data.get("replyTo", "")
        }


class MessageGenerator(OllamaGenerator):
    """Generate synthetic Message documents."""

    def get_prompt(self) -> str:
        return """Generate a realistic chat/messaging message with the following fields in JSON format:
{
  "content": "message content",
  "platform": "messaging platform (discord, telegram, signal, whatsapp, etc)",
  "user": "username",
  "isReply": boolean,
  "media": ["list of media URLs if any"],
  "messageId": "unique message ID",
  "replyTo": "message ID being replied to if isReply is true",
  "group": "group/server name",
  "channel": "channel name",
  "mentions": ["list of @mentioned usernames"]
}

Generate a diverse, realistic message. Return ONLY the JSON object, no additional text."""

    def parse_response(self, response: str) -> Dict[str, Any]:
        data = json.loads(response)
        return {
            "dtype": "message",
            "content": data.get("content", ""),
            "platform": data.get("platform", ""),
            "user": data.get("user", ""),
            "isReply": data.get("isReply", False),
            "media": data.get("media", []),
            "messageId": data.get("messageId", ""),
            "replyTo": data.get("replyTo", ""),
            "group": data.get("group", ""),
            "channel": data.get("channel", ""),
            "mentions": data.get("mentions", [])
        }


# Registry for easy extensibility
GENERATORS = {
    "person": PersonGenerator,
    "socialmediapost": SocialMediaPostGenerator,
    "message": MessageGenerator,
}


def get_generator(doc_type: str, **kwargs) -> OllamaGenerator:
    """Get a generator instance for the specified document type."""
    generator_class = GENERATORS.get(doc_type.lower())
    if not generator_class:
        raise ValueError(f"Unknown document type: {doc_type}")
    return generator_class(**kwargs)
