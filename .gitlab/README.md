# GitLab CI/CD Configuration

This directory contains GitLab CI/CD configuration and documentation for the TalkPipe project.

## Pipeline Overview

The GitLab CI/CD pipeline (`.gitlab-ci.yml`) provides comprehensive automation with the following stages:

### 1. Test Stage
- **Multi-version testing** on Python 3.11 and 3.12
- **Coverage reporting** with Cobertura format
- **Artifact generation** for coverage reports (HTML and XML)

### 2. Security Stage
- **Bandit** - Python static security analysis
- **Safety** - Dependency vulnerability scanning
- **GitLab SAST** - Built-in static application security testing
- **Dependency Scanning** - GitLab's dependency vulnerability detection
- **License Scanning** - License compliance checking
- **Secret Detection** - Credential and secret scanning
- **Container Scanning** - Docker image vulnerability assessment

### 3. Build Stage
- **Multi-stage Docker builds** using the optimized Fedora-based Dockerfile
- **Container registry** integration with GitLab Container Registry
- **Python package building** with wheel distribution
- **Automatic tagging** (latest, commit SHA, branch, version tags)

### 4. Deploy Stage
- **PyPI publishing** (manual trigger for tags)
- **Staging deployment** (automatic on main branch)
- **Production deployment** (manual trigger for tags)
- **GitLab Pages** for coverage reports
- **Registry cleanup** (scheduled job)

## GitLab-Specific Features

### Built-in Security Scanning
```yaml
include:
  - template: Security/SAST.gitlab-ci.yml
  - template: Security/Dependency-Scanning.gitlab-ci.yml
  - template: Security/License-Scanning.gitlab-ci.yml
  - template: Security/Secret-Detection.gitlab-ci.yml
  - template: Security/Container-Scanning.gitlab-ci.yml
```

### Container Registry Integration
Images are automatically pushed to GitLab Container Registry:
```
registry.gitlab.com/your-group/talkpipe:latest
registry.gitlab.com/your-group/talkpipe:<commit-sha>
registry.gitlab.com/your-group/talkpipe:<branch-name>
registry.gitlab.com/your-group/talkpipe:<tag-version>
```

### GitLab Pages
Coverage reports are automatically published to GitLab Pages at:
`https://your-group.gitlab.io/talkpipe/`

## Required GitLab CI/CD Variables

Configure these in `Settings > CI/CD > Variables`:

### Required for PyPI Publishing
- **`PYPI_API_TOKEN`** (Protected, Masked)
  - Type: Variable
  - Value: Your PyPI API token
  - Used in: `deploy:pypi` job

### Optional for Enhanced Deployments
- **`KUBE_CONFIG`** - Kubernetes configuration (if using K8s deployment)
- **`STAGING_URL`** - Staging environment URL
- **`PRODUCTION_URL`** - Production environment URL

### Automatic Variables (No Configuration Required)
- `CI_REGISTRY` - GitLab Container Registry URL
- `CI_REGISTRY_USER` - Registry username (automatic)
- `CI_REGISTRY_PASSWORD` - Registry password (automatic)
- `CI_COMMIT_SHA` - Current commit SHA
- `CI_COMMIT_REF_NAME` - Branch or tag name

## Pipeline Triggers

| Trigger | Branch/Tag | Jobs Executed |
|---------|------------|---------------|
| Push to any branch | `*` | test, security, build |
| Push to main | `main` | All + staging deploy |
| Git tag | `v*` | All + production deploy (manual) |
| Manual trigger | Any | All jobs |
| Scheduled | Any | cleanup:registry |

## Security Reports

GitLab provides integrated security dashboards:

1. **Security Dashboard**: Project > Security & Compliance > Security Dashboard
2. **Vulnerability Report**: Project > Security & Compliance > Vulnerability Report
3. **Dependency List**: Project > Security & Compliance > Dependency List
4. **License Compliance**: Project > Security & Compliance > License Compliance

## Local Testing

Test pipeline components locally:

```bash
# Install GitLab Runner locally
curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash
sudo apt-get install gitlab-runner

# Test jobs locally (requires gitlab-runner)
gitlab-runner exec docker test:python3.11
gitlab-runner exec docker security:bandit
gitlab-runner exec docker build:container
```

## Deployment Environments

### Staging Environment
- **Trigger**: Automatic on main branch pushes
- **URL**: Configurable via `STAGING_URL` variable
- **Purpose**: Integration testing and QA validation

### Production Environment  
- **Trigger**: Manual approval for tagged releases
- **URL**: Configurable via `PRODUCTION_URL` variable
- **Purpose**: Live production deployment

## Performance Optimizations

- **Caching**: Pip cache and pytest cache for faster builds
- **Parallel execution**: Multiple Python versions tested concurrently
- **Artifact reuse**: Build artifacts shared between jobs
- **Registry cleanup**: Scheduled cleanup of old images

## Monitoring and Notifications

Configure in `Settings > Integrations`:

- **Slack/Teams**: Pipeline status notifications
- **Email**: Failure notifications for critical jobs
- **Webhooks**: Custom integration endpoints

## Troubleshooting

### Common Issues

1. **Registry Push Fails**:
   ```bash
   # Check registry permissions
   # Ensure CI/CD variables are set correctly
   ```

2. **Security Scans Fail**:
   ```bash
   # Review security reports in GitLab UI
   # Check if vulnerabilities need addressing
   ```

3. **Test Failures**:
   ```bash
   # Run tests locally first
   gitlab-runner exec docker test:python3.11
   ```

4. **Deployment Issues**:
   ```bash
   # Verify environment variables are set
   # Check deployment job logs in GitLab UI
   ```

### Pipeline Optimization

- **Skip builds**: Add `[skip build]` to commit message
- **Parallel jobs**: Increase concurrent job limits in GitLab settings
- **Cache tuning**: Adjust cache paths for your specific dependencies

## Migration from GitHub Actions

Key differences when migrating from GitHub Actions:

| GitHub Actions | GitLab CI/CD |
|----------------|--------------|
| `workflow_dispatch` | Manual pipeline trigger |
| `secrets.GITHUB_TOKEN` | `CI_JOB_TOKEN` (automatic) |
| `ghcr.io` | `$CI_REGISTRY` |
| `codecov/codecov-action` | Built-in coverage reports |
| CodeQL | GitLab SAST |

## Advanced Configuration

### Custom Runners
For specialized hardware or software requirements:

```yaml
test:special:
  tags:
    - gpu
    - large-memory
```

### Dynamic Child Pipelines
For complex multi-project builds:

```yaml
trigger:child:
  trigger:
    include: child-pipeline.yml
```

### Conditional Jobs
Using rules for complex conditions:

```yaml
deploy:feature:
  rules:
    - if: $CI_COMMIT_BRANCH =~ /^feature\//
      when: manual
```

For additional help, check the GitLab CI/CD documentation or create an issue in the project repository.