# Multi-stage build for TalkPipe
# Stage 1: Build stage with all development dependencies
FROM fedora:latest AS builder

# Install system dependencies for building
RUN dnf update -y && \
    dnf install -y \
        python3 \
        python3-pip \
        python3-devel \
        git \
        gcc \
        gcc-c++ \
        make \
        cmake \
        pkg-config \
        libxml2-devel \
        libxslt-devel \
        openssl-devel \
        && dnf clean all

# Create build user
RUN groupadd -r builder && useradd -r -g builder -m builder

# Set up build environment
WORKDIR /build
RUN chown builder:builder /build
USER builder

# Copy source files
#COPY --chown=builder:builder pyproject.toml README.md LICENSE ./
COPY --chown=builder:builder pyproject.toml LICENSE ./
COPY --chown=builder:builder src/ src/
COPY --chown=builder:builder tests/ tests/

# Install Python dependencies and build the package
RUN python3 -m pip install --upgrade pip setuptools wheel build
RUN python3 -m pip install numpy pandas matplotlib scikit-learn scipy
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_TALKPIPE=0.1.0
RUN python3 -m pip install --user -e .[dev,all]
RUN python3 -m pytest --log-cli-level=DEBUG
RUN python3 -m build --wheel

# Stage 2: Runtime stage with minimal dependencies
FROM fedora:latest AS runtime

# Install only runtime system dependencies
RUN dnf update -y && \
    dnf install -y \
        python3 \
        python3-pip \
        git \
        && dnf clean all && \
        rm -rf /var/cache/dnf

# Create application user with specific UID/GID for better security
RUN groupadd -r -g 1001 app && \
    useradd -r -u 1001 -g app -s /sbin/nologin \
        -c "TalkPipe Application User" app

# Set up application directory
WORKDIR /app
RUN mkdir -p /app/data && \
    chown -R app:app /app

# Copy the built wheel from builder stage
COPY --from=builder --chown=app:app /build/dist/*.whl /tmp/

# Install runtime Python dependencies and the application
RUN python3 -m pip install --no-cache-dir --upgrade pip && \
    python3 -m pip install --no-cache-dir \
        numpy pandas matplotlib scikit-learn scipy && \
    WHEEL_FILE=$(ls /tmp/*.whl) && \
    python3 -m pip install --no-cache-dir "${WHEEL_FILE}[all]" && \
    rm -f /tmp/*.whl

# Copy only necessary runtime files
COPY --chown=app:app pyproject.toml ./

# Create data volume mount point
VOLUME ["/app/data"]

# Switch to non-root user
USER app

# Security: Run as non-root, read-only filesystem capability
# Health check to ensure the application starts correctly
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python3 -c "import talkpipe; print('TalkPipe loaded successfully')" || exit 1

# Set environment variables for better container behavior
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Default command with parameterized script execution
CMD ["python3", "-m", "talkpipe.app.chatterlang_script", "--load-module", "data/custom_module.py", "--script", "TALKPIPE_SCRIPT"]