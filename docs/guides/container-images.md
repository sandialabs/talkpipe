# Container images (GitHub Container Registry)

Official TalkPipe images are built in CI and published to **GitHub Container Registry** (GHCR).

- **Package page:** [github.com/sandialabs/talkpipe/pkgs/container/talkpipe](https://github.com/sandialabs/talkpipe/pkgs/container/talkpipe)
- **Image reference:** `ghcr.io/sandialabs/talkpipe`

Use **Docker** or **Podman** the same way; the examples below use `docker`—substitute `podman` if you prefer.

Set an image tag once (pin a [release](https://github.com/sandialabs/talkpipe/releases) version or use `latest`):

```bash
IMAGE=ghcr.io/sandialabs/talkpipe:latest
# IMAGE=ghcr.io/sandialabs/talkpipe:0.11.7   # example pinned version
```

## Multi-platform releases

When a **GitHub release** is published, CI pushes a **multi-platform** manifest:

- `linux/amd64` — typical x86_64 servers, Intel Macs (Linux VM), Windows (Docker Desktop / WSL2)
- `linux/arm64` — Apple Silicon Macs, many ARM64 Linux servers (for example AWS Graviton)

Your client pulls the correct architecture automatically. To list platforms in a release image (replace the tag with the version you use):

```bash
docker manifest inspect ghcr.io/sandialabs/talkpipe:0.11.7 | grep architecture
```

Non-release workflow runs (pushes and pull requests) still publish images for CI, but those builds are **single-platform** (`linux/amd64` only) for faster pipelines. For reproducible, portable deployments, use an image built from a **release** tag.

## Tags and versions

Images are tagged from the same metadata CI uses for releases and branches. Useful patterns:

| Tag | When to use |
|-----|----------------|
| `latest` | Latest **stable** release (not pre-releases tagged as alpha/beta). Good for quick starts; pin a version for production. |
| `experimental` | Latest **pre-release** (alpha/beta) GitHub release, when applicable. |
| `0.11.7` (example) | Exact release (**full semantic version**). Best for reproducible deploys. |
| `0.11` | **Major.minor** line—floats to the newest patch in that minor series for that release stream. |
| Branch or PR refs | Built from CI on pushes/PRs; **amd64 only**; useful for testing unreleased commits. |
| Git SHA | Immutable pointer to the exact image built for a commit. |

Replace `0.11.7` with the version you want from the [releases](https://github.com/sandialabs/talkpipe/releases) page.

## Pull an image

Public images can be pulled without logging in to GHCR (subject to GitHub’s normal rate limits for anonymous pulls):

```bash
docker pull ghcr.io/sandialabs/talkpipe:0.11.7
docker pull ghcr.io/sandialabs/talkpipe:latest
```

If your environment requires authentication (for example private registry mirrors or organization policy):

```bash
docker login ghcr.io
# Use a GitHub personal access token with `read:packages` where prompted for a password.
```

## Example commands

The image includes TalkPipe’s published CLIs. Override the container command after the image name.

**HTTP servers** default to loopback inside the container, so **published ports (`-p`) from the host will not work** unless the process binds to all interfaces. Use **`--host 0.0.0.0`** (`chatterlang_workbench`) or **`-o 0.0.0.0`** (`chatterlang_serve`, `serverag`). Then open **`http://127.0.0.1:<port>`** on the host (if you map the port to `127.0.0.1` only, prefer that URL over `http://localhost:...`, which may resolve to IPv6 and miss the forward).

### Help and non-network CLIs

```bash
docker run --rm "$IMAGE" chatterlang_workbench --help
docker run --rm "$IMAGE" chatterlang_serve --help
docker run --rm "$IMAGE" serverag --help
docker run --rm "$IMAGE" makevectordatabase --help
docker run --rm "$IMAGE" chatterlang_script --help
docker run --rm "$IMAGE" chatterlang_reference_generator --help
docker run --rm "$IMAGE" talkpipe_plugins --help
```

### ChatterLang workbench (web UI, default port 4143)

```bash
docker run --rm -p 127.0.0.1:4143:4143 "$IMAGE" \
  chatterlang_workbench --host 0.0.0.0
```

### chatterlang_serve (default port 2025)

Add `--script`, `--form-config`, and other options as needed; binding uses **`-o`** for host:

```bash
docker run --rm -p 127.0.0.1:2025:2025 "$IMAGE" \
  chatterlang_serve -o 0.0.0.0 -p 2025
```

### serverag — RAG web UI (default port 2026)

Mount your LanceDB directory and pass `--path` (see also **[makevectordatabase and serverag](makevectordatabase-and-serverag.md)**):

```bash
docker run --rm -p 127.0.0.1:2026:2026 -v "$PWD/mydb:/app/data:ro" "$IMAGE" \
  serverag --path /app/data -o 0.0.0.0
```

### makevectordatabase (one-shot; no `--host`)

```bash
docker run --rm -v "$PWD/docs:/app/docs" -v "$PWD/mydb:/app/data" "$IMAGE" \
  makevectordatabase "/app/docs/*.md" --path /app/data
```

### RAG: end-to-end (build DB, then serve)

```bash
docker run --rm -v "$PWD/docs:/app/docs" -v "$PWD/mydb:/app/data" "$IMAGE" \
  makevectordatabase "/app/docs/*.md" --path /app/data

docker run --rm -p 127.0.0.1:2026:2026 -v "$PWD/mydb:/app/data" "$IMAGE" \
  serverag --path /app/data -o 0.0.0.0
```

## Build details (maintainers)

CI configuration and tag behavior are summarized in [.github/CICD.md](../../.github/CICD.md).
