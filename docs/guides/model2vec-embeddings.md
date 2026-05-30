# Model2vec embeddings

Run lightweight static embedding models **inside your Python process** with no API calls and
no Ollama server. Models are cached on disk via the Hugging Face Hub; after precaching, you
can run fully offline with `HF_HUB_OFFLINE=1`.

Model2vec distills sentence-transformers into fixed token lookup tables. The result is much
smaller and faster than full transformer inference, with competitive quality for many retrieval
tasks. For highest embedding quality or models you already run in Ollama, use `source="ollama"`
or `source="openai"` instead.

---

## Install

```bash
pip install talkpipe[model2vec]
# Or: pip install talkpipe[all]   # includes model2vec
```

The base `model2vec` package depends mainly on numpy and tokenizers — no PyTorch at inference
time.

---

## Quick start

```python
from talkpipe.chatterlang import compile

fn = compile(
    "| llmEmbed[model='minishlab/potion-base-8M', source='model2vec']"
).as_function(single_in=True, single_out=False)

vector = list(fn("A paragraph to embed."))[0]
print(len(vector))  # 256 for the default model
```

Or set defaults in `~/.talkpipe.toml`:

```toml
default_embedding_model_name = "minishlab/potion-base-8M"
default_embedding_model_source = "model2vec"
```

Then use `| llmEmbed` without explicit `model` / `source`.

---

## Default model

The default model is **`minishlab/potion-base-8M`**:

- ~7.5M params, ~30 MB on disk
- 256 dimensions, L2-normalized (`model.normalize == True`)
- English; distilled from `BAAI/bge-base-en-v1.5`

Other options from [MinishLab on Hugging Face](https://huggingface.co/minishlab):

| Model | Params | Notes |
|-------|--------|-------|
| `minishlab/potion-base-4M` | 3.7M | Smaller/faster |
| `minishlab/potion-base-2M` | 1.8M | Smallest English potion |
| `minishlab/M2V_multilingual_output` | 471M | Multilingual; much larger |

Switching models changes vector dimension — **re-index** existing vector databases.

---

## Precache for offline use

Download models at build time so runtime needs no network:

```bash
talkpipe_precache_model2vec precache minishlab/potion-base-8M \
  --revision <commit-sha> \
  --cache-dir /path/to/hf-cache
```

**Docker example:**

```dockerfile
RUN talkpipe_precache_model2vec precache minishlab/potion-base-8M --revision abc123
ENV HF_HUB_OFFLINE=1
```

Pin `--revision` to a commit SHA for reproducible builds.

---

## Configuration

Optional settings in `~/.talkpipe.toml` or via `TALKPIPE_*` environment variables:

| Key | Purpose |
|-----|---------|
| `MODEL2VEC_REVISION` | Pin HF commit SHA |
| `MODEL2VEC_CACHE_DIR` | Override HF cache root |

Normalization is defined by the model itself (not configurable at runtime).

---

## Python API

For scripts outside ChatterLang:

```python
from talkpipe.llm.model2vec_embeddings import Model2VecEmbedder, precache_model

precache_model("minishlab/potion-base-8M")

embedder = Model2VecEmbedder()
vector = embedder.embed_one("Paragraph text.")
batch = embedder.embed(["first", "second"])
```

Pin to a specific HF commit by passing `revision="<commit-sha>"` to either
`precache_model` or `Model2VecEmbedder(...)` for reproducible builds.

---

## RAG and vector databases

Use `embedding_source="model2vec"` anywhere embeddings are configured:

```bash
makevectordatabase docs/*.md --path ./vault \
  --embedding_model minishlab/potion-base-8M \
  --embedding_source model2vec
```

ChatterLang:

```python
"| makeVectorDatabase[path='tmp://kb', embedding_model='minishlab/potion-base-8M', embedding_source='model2vec', embedding_field='text']"
```

See [makevectordatabase and serverag](makevectordatabase-and-serverag.md) and
[Model and source configuration](model-and-source-configuration.md).

---

## Related

- [Model and source configuration](model-and-source-configuration.md) — defaults and precedence
- [model2vec on GitHub](https://github.com/MinishLab/model2vec)
