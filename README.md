# StarIntel Synthetic Data Generator

Generate synthetic StarIntel documents using Ollama for OSINT testing and development.

## Features

- Generates Person, SocialMediaPost, and Message documents
- Uses Ollama for realistic synthetic data
- Outputs NDJSON to stdout for easy piping
- Extensible architecture for adding new document types

## Setup

```bash
nix develop
```

Ensure Ollama is running:
```bash
ollama serve
```

Pull a model:
```bash
ollama pull llama3.2
```

## Usage

Generate documents:
```bash
# Generate 5 people
python main.py person -n 5

# Generate 10 social media posts
python main.py socialmediapost -n 10

# Generate 20 messages with custom dataset
python main.py message -n 20 -d mydata

# Use a different model
python main.py person -n 5 -m mistral

# Save to file
python main.py person -n 100 > people.ndjson
```

## Extending with New Document Types

To add a new document type:

1. **Create a Generator Class** in `generators.py`:

```python
class NewDocTypeGenerator(OllamaGenerator):
    """Generate synthetic NewDocType documents."""

    def get_prompt(self) -> str:
        return """Generate a realistic document with fields in JSON format:
{
  "field1": "value",
  "field2": number
}
Return ONLY the JSON object, no additional text."""

    def parse_response(self, response: str) -> Dict[str, Any]:
        data = json.loads(response)
        return {
            "dtype": "newdoctype",
            "field1": data.get("field1", ""),
            "field2": data.get("field2", 0)
        }
```

2. **Register in GENERATORS dict** in `generators.py`:

```python
GENERATORS = {
    "person": PersonGenerator,
    "socialmediapost": SocialMediaPostGenerator,
    "message": MessageGenerator,
    "newdoctype": NewDocTypeGenerator,  # Add here
}
```

3. **Add creation logic** in `main.py`:

```python
elif doc_type == "newdoctype":
    doc = new_newdoctype(
        dataset=dataset,
        field1=raw_data.get("field1", ""),
        field2=raw_data.get("field2", 0)
    )
```

4. **Use it**:

```bash
python main.py newdoctype -n 10
```

## Flake Outputs

- `packages.x86_64-linux.default` - Built synthdata CLI tool
- `devShells.x86_64-linux.default` - Development environment with all dependencies
- `apps.x86_64-linux.default` - Run synthdata CLI
- `apps.x86_64-linux.ipython` - Run IPython for interactive development

## Options

- `-n, --count` - Number of documents to generate (default: 10)
- `-d, --dataset` - Dataset name (default: synthdata)
- `-m, --model` - Ollama model to use (default: llama3.2)
- `-u, --url` - Ollama base URL (default: http://localhost:11434)
