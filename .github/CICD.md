# GitHub CI/CD Configuration

This directory contains the GitHub Actions workflows and configuration for the TalkPipe project's automated CI/CD pipeline.

## Files Overview

### Workflows (`workflows/`)

#### `ci-cd.yml` - Main CI/CD Pipeline
Comprehensive pipeline that runs on:
- Pushes to `main` and `develop` branches  
- Pull requests to `main` and `develop`
- GitHub releases

**Pipeline Jobs:**
1. **Test** - Multi-version Python testing (3.11, 3.12) with coverage
2. **Security Scan** - SAST and dependency vulnerability scanning
3. **Build Container** - Docker image build/push with container security scan
4. **CodeQL Analysis** - GitHub's semantic code analysis
5. **Publish Package** - Automated PyPI publishing on releases

### Configuration Files

- **`dependabot.yml`** - Automated dependency updates (weekly schedule)
- **`SECURITY.md`** - Security policy and vulnerability reporting guidelines

### Root Level Security Files

- **`.bandit`** - Configuration for Bandit static security analysis
- **`.dockerignore`** - Optimized Docker build context exclusions

## Security Scanning

The pipeline includes multiple layers of security scanning:

- **Bandit** - Python static analysis security testing (SAST)
- **Safety** - Python dependency vulnerability scanning  
- **Trivy** - Container image vulnerability scanning
- **CodeQL** - Semantic code analysis for security issues
- **Dependabot** - Automated dependency update PRs

## Container Registry

Docker images are built and pushed to GitHub Container Registry:
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
# Run tests with coverage (matches CI)
pytest --cov=src --cov-report=xml --cov-report=html

# Run security scans
bandit -r src/
safety check

# Build container (matches CI)
docker build -t talkpipe:local .

# Run container security scan
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy image talkpipe:local
```

## Workflow Triggers

| Event | Trigger | Jobs Run |
|-------|---------|----------|
| Push to main/develop | Automatic | All jobs |
| Pull Request | Automatic | All except publish |
| Release published | Automatic | All jobs + PyPI publish |
| Manual trigger | `workflow_dispatch` | All jobs |

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
   - Add exclusions to `.bandit` if needed

For additional help, check the Actions tab logs or create an issue in the repository.