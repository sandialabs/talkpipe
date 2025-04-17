FROM python:3.11

# Set working directory
WORKDIR /app

# Install PDM
RUN pip install pdm

# Copy pyproject.toml into the container
COPY pyproject.toml ./pyproject.toml

# Run pdm lock, export deps to requirements.txt, and install
RUN pdm lock && \
    pdm export --without-hashes --dev -o requirements.txt && \
    pip install -r requirements.txt && \
    rm requirements.txt

# Install the basics of the scientific computing stack for analytics
RUN pip install numpy pandas matplotlib scikit-learn scipy