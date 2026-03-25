# makevectordatabase and serverag

**Create a vector database from your documents and run a RAG web server in two commands.**

The `makevectordatabase` and `serverag` commands provide a streamlined workflow for document RAG (Retrieval-Augmented Generation): index your files into a LanceDB vector database, then query them through a web UI or interactive CLI. No ChatterLang scripts required.

---

## Overview

| Command | Purpose |
|---------|---------|
| **makevectordatabase** | Create a LanceDB vector database from documents (files or glob patterns) |
| **serverag** | Run a RAG server on an existing database—web UI or interactive CLI |

Together they form a minimal path from raw documents to a queryable RAG interface.

---

## Prerequisites

- **TalkPipe** with LLM support: `pip install talkpipe[ollama]` or `pip install talkpipe[all]`
- **Embedding model**: Ollama with an embedding model (e.g. `ollama pull mxbai-embed-large`)
- **Completion model** (for serverag): Ollama with an LLM (e.g. `ollama pull llama3.2`)
- **Configuration**: Set `DEFAULT_EMBEDDING_MODEL`, `DEFAULT_EMBEDDING_SOURCE`, `DEFAULT_LLM_MODEL`, and `DEFAULT_LLM_SOURCE` in `~/.talkpipe.toml` or pass them on the command line

See [Configuration](../architecture/configuration.md) for details.

---

## Step 1: Create a Vector Database

Use `makevectordatabase` to process documents and build a LanceDB index.

### Basic Usage

```bash
makevectordatabase "docs/*.md" --path ./mydb
```

- **First argument**: File path or glob pattern (e.g. `"docs/*.md"`, `"data/*.pdf"`, `"/path/to/file.txt"`)
- **`--path`**: Directory where the LanceDB database will be created (required)

### Common Options

| Option | Description | Default |
|--------|-------------|---------|
| `--path` | Path for the LanceDB database | Required |
| `--embedding_model` | Embedding model name | Config default |
| `--embedding_source` | Embedding source (e.g. `ollama`) | Config default |
| `--table_name` | Table name in the database | `docs` |
| `--chunk_size` | Characters per text chunk | 300 |
| `--overwrite` | Overwrite existing table | False |
| `--doc_id_field` | Field for document ID; `None` = unique IDs per chunk | None |

### Example with Options

```bash
makevectordatabase "content/**/*.md" --path ./vault \
  --embedding_model mxbai-embed-large \
  --embedding_source ollama \
  --table_name docs \
  --chunk_size 400 \
  --overwrite
```

Supported file types include Markdown, text, and PDF (with `pip install talkpipe[pypdf]`).

---

## Step 2: Run the RAG Server

Use `serverag` to query the database via web UI or CLI.

### Web UI Mode

```bash
serverag --path ./mydb
```

- Opens a web server (default: `http://localhost:2026`)
- Navigate to `/stream` for the chat-style interface
- Enter questions in the prompt field; press Enter to submit
- Responses are rendered as markdown with source citations

### Interactive CLI Mode

```bash
serverag --path ./mydb --interactive
```

- Runs a REPL in the terminal
- Type questions and press Enter; answers print below
- Press Ctrl+D to exit

### Common Options

| Option | Description | Default |
|--------|-------------|---------|
| `--path` | Path to the LanceDB database | Required |
| `-p, --port` | Port for web server | 2026 |
| `-o, --host` | Host to bind to | localhost |
| `--limit` | Number of search results to retrieve | 5 |
| `--table_name` | Table name (must match makevectordatabase) | `docs` |
| `--completion_model` | LLM for answers | Config default |
| `--completion_source` | LLM source (e.g. `ollama`) | Config default |
| `--embedding_model` | Embedding model (must match makevectordatabase) | Config default |
| `--embedding_source` | Embedding source | Config default |
| `--interactive` | Use CLI REPL instead of web server | False |
| `--api_key` | API key for authentication | None |
| `--require_auth` | Require API key | False |

### Example with Options

```bash
serverag --path ./vault \
  --port 8080 \
  --limit 8 \
  --title "My Document Q&A"
```

---

## End-to-End Example

```bash
# 1. Create the vector database from Markdown files
makevectordatabase "docs/*.md" --path ~/Desktop/myvault

# 2. Start the RAG web server
serverag --path ~/Desktop/myvault
```

Then open `http://localhost:2026/stream` in your browser and ask questions about your documents.

---

## Running in Containers (Docker and Podman)

You can run `makevectordatabase` and `serverag` in containers using the [TalkPipe image](https://github.com/sandialabs/talkpipe/pkgs/container/talkpipe). The same commands work with **Docker** and **Podman**—replace `docker` with `podman` if you use Podman. For a custom setup (e.g., extra Python packages or a fixed default command), create a separate Dockerfile based on that image.

### Minimal Dockerfile for serverag

Create `Dockerfile.serverag`:

```dockerfile
FROM ghcr.io/sandialabs/talkpipe:latest

# Optional: install additional Python packages
# RUN pip install --no-cache-dir some-extra-package

CMD ["serverag", "--path", "/app/data", "--host", "0.0.0.0"]
```

Build and run:

```bash
# Build the image
docker build -f Dockerfile.serverag -t my-serverag .

# Run with your database mounted at /app/data
docker run -p 2026:2026 -v ./mydb:/app/data my-serverag
```

Use `--host 0.0.0.0` so the server accepts connections from outside the container. Omit it only if you run in interactive mode (`--interactive`).

### Running makevectordatabase in a container

`makevectordatabase` is a one-shot command. Run it with the base image and override the command:

```bash
# Mount documents and output directory; override CMD with makevectordatabase
docker run -v ./docs:/app/docs -v ./mydb:/app/data \
  ghcr.io/sandialabs/talkpipe \
  makevectordatabase "/app/docs/*.md" --path /app/data
```

Or create `Dockerfile.makevectordatabase` for a fixed document set:

```dockerfile
FROM ghcr.io/sandialabs/talkpipe:latest

COPY --chown=app:app ./docs /app/docs

CMD ["makevectordatabase", "/app/docs/*.md", "--path", "/app/data"]
```

Build and run with a volume for the output database:

```bash
docker build -f Dockerfile.makevectordatabase -t my-makevectordb .
docker run -v ./mydb:/app/data my-makevectordb
```

### End-to-end with containers

```bash
# 1. Build the database (one-shot)
docker run -v $(pwd)/docs:/app/docs -v $(pwd)/mydb:/app/data \
  ghcr.io/sandialabs/talkpipe \
  makevectordatabase "/app/docs/*.md" --path /app/data

# 2. Start the RAG server
docker run -p 2026:2026 -v $(pwd)/mydb:/app/data \
  ghcr.io/sandialabs/talkpipe \
  serverag --path /app/data --host 0.0.0.0
```

Then open `http://localhost:2026/stream` in your browser.

---

## Configuration

Both commands use TalkPipe's configuration system. Set defaults in `~/.talkpipe.toml`:

```toml
# Embedding (used by both makevectordatabase and serverag)
DEFAULT_EMBEDDING_MODEL = "mxbai-embed-large"
DEFAULT_EMBEDDING_SOURCE = "ollama"

# Completion (serverag only)
DEFAULT_LLM_MODEL = "llama3.2"
DEFAULT_LLM_SOURCE = "ollama"
```

Or pass values on the command line to override.

---

## Relationship to Other Documentation

- **Tutorial 2: Search & RAG** — Uses ChatterLang scripts for more control over indexing and RAG behavior. The `makevectordatabase` and `serverag` commands wrap similar pipelines with sensible defaults.
- **[chatterlang_serve](../api-reference/chatterlang-server.md)** — serverag uses ChatterlangServer under the hood; see that reference for API endpoints and form configuration.
- **[Configuration](../architecture/configuration.md)** — How to set embedding and LLM defaults.

---

## Troubleshooting

| Issue | Cause | Fix |
|-------|-------|-----|
| "embedding_model not specified" | No config or CLI value | Set in `~/.talkpipe.toml` or pass `--embedding_model` |
| Ollama connection error | Ollama not running | Start Ollama: `ollama serve` |
| Model not found | Model not installed | Run `ollama pull mxbai-embed-large` and `ollama pull llama3.2` |
| Port already in use | Another process on port | Use `--port 8080` (or another port) |
| No relevant information found | Query not in documents | Try rephrasing or increasing `--limit` |

---

*Last reviewed: 20260307*
