# GitHub CI/CD Configuration

This directory contains the GitHub Actions workflows and configuration for the TalkPipe project's automated CI/CD pipeline.

## Files Overview

### Workflows (`workflows/`)

#### `ci-cd.yml` - Main CI/CD Pipeline
Comprehensive pipeline that runs on:
- Pushes to `main` and topic branches (`bugfix/**`, `feature/**`, `chore/**`)  
- Pull requests targeting `main`
- GitHub releases

**Pipeline Jobs:**

Host-neutral jobs run identically on GitHub Actions and on any other
Actions-compatible runner; jobs that need github.com are guarded with
`if: github.server_url == 'https://github.com'`.

| Job | Runs | What it does |
|---|---|---|
| `test` | everywhere, matrix 3.11 / 3.12 / 3.13 | `pytest --cov=src`; the `[tool.coverage.report] fail_under` floor in `pyproject.toml` fails the job if coverage drops below it. Coverage is uploaded to Codecov from the 3.11 leg. |
| `lint` | everywhere, 3.11 | `ruff check`, `ruff format --check`, `mypy` — all gating, no advisory mode — plus an entry-point drift check (regenerates the `talkpipe.sources`/`talkpipe.segments` tables from the `@register_*` decorators and fails on any diff to `pyproject.toml`). |
| `package` | everywhere, 3.11 | Builds the sdist and wheel, `twine check`s them, installs the wheel into a clean venv, imports the package, runs `chatterlang_script --help`, and loads every declared entry point. Catches packaging breakage before release time. |
| `lockfile-check` | everywhere | `uv lock --check` — the committed `uv.lock` must match `pyproject.toml`. Installs nothing; CI installs with pip on purpose. |
| `security-scan` | everywhere; needs `test`, `lint` | Bandit (`-c pyproject.toml`, the `[tool.bandit]` table) and Safety. Uses the commercial database when `SAFETY_API_KEY` is set and falls back to the free `safety check` database when it is not (secrets are not passed to pull-request runs); both fail the build on a known vulnerability. |
| `build-container` | github.com only | Docker image build and push to ghcr.io, Trivy scan; multi-architecture (linux/amd64, linux/arm64) on release only. |
| `codeql-analysis` | github.com only | GitHub's semantic code analysis. |
| `publish-package` | on a published release; needs `test`, `lint`, `package`, `security-scan` | `python -m build`, `twine check`, upload to PyPI. Does not depend on the container job, so publishing is not blocked where that job is skipped. |

### Configuration Files

- **`dependabot.yml`** - Automated dependency updates (weekly schedule)
- **`SECURITY.md`** - Security policy and vulnerability reporting guidelines

### Root Level Security Files

- **`[tool.bandit]` in `pyproject.toml`** - Configuration for Bandit static security analysis
- **`.dockerignore`** - Optimized Docker build context exclusions

## Security Scanning

The pipeline includes multiple layers of security scanning:

- **Bandit** - Python static analysis security testing (SAST)
- **Safety** - Python dependency vulnerability scanning  
- **Trivy** - Container image vulnerability scanning
- **CodeQL** - Semantic code analysis for security issues
- **Dependabot** - Automated dependency update PRs

## Container Registry

Docker images are built and pushed to GitHub Container Registry. On **release**, images are built for multiple architectures (linux/amd64, linux/arm64). On push/PR, only linux/amd64 is built. Multi-arch covers:
- **linux/amd64**: x86_64 Linux, Windows (Docker Desktop/WSL2), Intel Macs
- **linux/arm64**: Apple Silicon Macs, ARM64 Linux servers (e.g. AWS Graviton)

Images are available at:
```
ghcr.io/sandialabs/talkpipe:latest
ghcr.io/sandialabs/talkpipe:<branch-name>
ghcr.io/sandialabs/talkpipe:<version>
```

## Required Repository Secrets

To enable full functionality, set these secrets in your GitHub repository settings (`Settings > Secrets and variables > Actions`):

### Required for PyPI Publishing
- **`PYPI_API_TOKEN`** - PyPI API token for automated package publishing
  - Create at: https://pypi.org/manage/account/token/
  - Scope: Entire account or specific to talkpipe project
  - Used in: Package publishing job (triggered on releases)

### Automatic Secrets (No Action Required)
- **`GITHUB_TOKEN`** - Automatically provided by GitHub Actions
  - Used for: Container registry authentication, uploading artifacts, CodeQL results

## Setup Instructions

1. **Enable GitHub Container Registry** (if not already enabled):
   - Go to repository `Settings > General`
   - Scroll to "Features" section
   - Ensure "Packages" is enabled

2. **Set PyPI Token**:
   ```bash
   # In repository Settings > Secrets and variables > Actions
   # Add new repository secret:
   Name: PYPI_API_TOKEN
   Secret: pypi-your-token-here
   ```

3. **Configure Dependabot** (optional customization):
   - Edit `.github/dependabot.yml` to adjust reviewers/assignees
   - Default: weekly updates on Mondays at 9 AM UTC

## Testing Locally

Before pushing, you can test components locally:

```bash
# Run tests with coverage (matches CI; fails below the fail_under floor)
pytest --cov=src --cov-report=term --cov-report=xml --cov-report=html

# Lint / format / types (matches CI)
ruff check . && ruff format --check . && mypy

# Entry-point drift check (matches CI)
python .cursor/skills/update-entry-points/scripts/update_entry_points.py && git diff --exit-code -- pyproject.toml

# Packaging smoke test (matches CI)
python -m build && twine check dist/*

# Run security scans
bandit -c pyproject.toml -r src/
export SAFETY_API_KEY=your-key   # optional; links results to Safety Platform
safety scan

# Build container (matches CI)
docker build -t talkpipe:local .

# Run container security scan
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image talkpipe:local
```

## Workflow Triggers

| Event | Trigger | Jobs Run |
|-------|---------|----------|
| Push to main | Automatic | All jobs |
| Pull Request | Automatic | All except publish |
| Release published | Automatic | All jobs + PyPI publish |

## Monitoring

- **Test Results**: Visible in Actions tab and PR checks
- **Coverage Reports**: Uploaded to Codecov (if configured)
- **Security Issues**: Reported in Security tab (CodeQL, Trivy)
- **Container Images**: Available in Packages tab

## Troubleshooting

**Common Issues:**

1. **PyPI Publishing Fails**:
   - Verify `PYPI_API_TOKEN` is set correctly
   - Ensure token has sufficient permissions
   - Check package version doesn't already exist

2. **Container Build Fails**:
   - Check Dockerfile syntax
   - Verify base image availability
   - Review build logs in Actions tab

3. **Tests Fail**:
   - Run tests locally first
   - Check dependency compatibility
   - Review test logs in Actions tab

4. **Security Scans Fail**:
   - Review Bandit/Safety reports
   - Update vulnerable dependencies
   - Add exclusions to `[tool.bandit]` in `pyproject.toml` if needed

For additional help, check the Actions tab logs or create an issue in the repository.