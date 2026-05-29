# Local embeddings

Run Hugging Face embedding models **inside your Python process** with no API calls and no
Ollama server. Models are cached on disk via the Hugging Face Hub; after precaching, you
can run fully offline with `HF_HUB_OFFLINE=1`.

This is an **opt-in, heavy** install path. For most local embedding workflows, `source="ollama"`
is simpler and lighter. Use `source="local"` when you need air-gapped deployment, Docker
images with baked-in models, or explicit HF model/revision pins.

---

## Install

```bash
pip install talkpipe[local-embeddings]
```

This pulls in `sentence-transformers` and PyTorch (~300 MB–1+ GB depending on platform).
It is **not** included in `talkpipe[all]`. Use `talkpipe[all-local]` if you want every
optional feature including local embeddings.

---

## Quick start

```python
from talkpipe.chatterlang import compile

fn = compile(
    "| llmEmbed[model='jinaai/jina-embeddings-v2-base-en', source='local']"
).as_function(single_in=True, single_out=False)

vector = list(fn("A paragraph to embed."))[0]
print(len(vector))
```

Or set defaults in `~/.talkpipe.toml`:

```toml
default_embedding_model_name = "jinaai/jina-embeddings-v2-base-en"
default_embedding_model_source = "local"
```

Then use `| llmEmbed` without explicit `model` / `source`.

---

## Default model

The default model is **`jinaai/jina-embeddings-v2-base-en`**:

- 8192-token context (paragraph-length inputs without silent truncation)
- 768 dimensions, ~330 MB weights
- L2-normalized vectors (dot product equals cosine similarity)

Other long-context options:

| Model | Context | Dims | Weights (approx.) |
|-------|---------|------|-------------------|
| `nomic-ai/nomic-embed-text-v1.5` | 8192 | 768 | ~550 MB |
| `BAAI/bge-m3` | 8192 | 1024 | ~2.3 GB |

Switching models changes vector dimension — **re-index** existing vector databases.

---

## Precache for offline use

Download models at build time so runtime needs no network:

```bash
talkpipe_precache_embeddings precache jinaai/jina-embeddings-v2-base-en \
  --revision <commit-sha> \
  --cache-dir /path/to/hf-cache
```

Tokenizer-only download (~1 MB) for token counting without loading weights:

```bash
talkpipe_precache_embeddings precache jinaai/jina-embeddings-v2-base-en --tokenizer-only
```

**Docker example:**

```dockerfile
RUN talkpipe_precache_embeddings precache jinaai/jina-embeddings-v2-base-en --revision abc123
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
```

Pin `--revision` to a commit SHA for reproducible builds; branch names can be force-pushed.

---

## Configuration

Optional settings in `~/.talkpipe.toml` or via `TALKPIPE_*` environment variables:

| Key | Purpose |
|-----|---------|
| `LOCAL_EMBEDDING_REVISION` | Pin HF commit SHA |
| `LOCAL_EMBEDDING_DEVICE` | `cpu`, `cuda`, `mps`, or omit for auto-detect |
| `LOCAL_EMBEDDING_CACHE_DIR` | Override HF cache root |
| `LOCAL_EMBEDDING_TRUST_REMOTE_CODE` | Default `true` (required for Jina/Nomic custom code) |
| `LOCAL_EMBEDDING_NORMALIZE` | Default `true` (L2-normalize output vectors) |

---

## Python API

For scripts outside ChatterLang:

```python
from talkpipe.llm.local_embeddings import LocalEmbedder, precache_model

precache_model("jinaai/jina-embeddings-v2-base-en", revision="abc123")

embedder = LocalEmbedder()
vector = embedder.embed_one("Paragraph text.")
batch = embedder.embed(["first", "second"])
```

---

## RAG and vector databases

Use `embedding_source="local"` anywhere embeddings are configured:

```bash
makevectordatabase docs/*.md --path ./vault \
  --embedding_model jinaai/jina-embeddings-v2-base-en \
  --embedding_source local
```

ChatterLang:

```python
"| makeVectorDatabase[path='tmp://kb', embedding_model='jinaai/jina-embeddings-v2-base-en', embedding_source='local', embedding_field='text']"
```

See [makevectordatabase and serverag](makevectordatabase-and-serverag.md) and
[Model and source configuration](model-and-source-configuration.md).

---

## Related

- [Local embeddings plan](../architecture/local-embeddings-plan.md) — design notes
- [Model and source configuration](model-and-source-configuration.md) — defaults and precedence
