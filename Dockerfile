FROM python:3.11-slim

# Create a non-root user
RUN groupadd -r talkpipe && useradd -r -g talkpipe talkpipe
RUN  apt-get update && apt-get install -y git

# Set working directory
WORKDIR /app

# Install the basics of the scientific computing stack for analytics
RUN pip install numpy pandas matplotlib scikit-learn scipy

COPY . .

# Create a data directory under the app directory
RUN mkdir -p /app/data

# Declare /usr/src/app/data as a volume
VOLUME /app/data

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/
COPY tests/ tests/
COPY .git/ .git/

RUN pip install --upgrade pip
RUN pip install -e .[dev]
RUN pytest --log-cli-level=DEBUG
RUN rm -fr .git
RUN rm -fr tests

# Change ownership of the app directory to the talkpipe user
RUN chown -R talkpipe:talkpipe /app

# Switch to the non-root user
USER talkpipe

CMD ["python", "-m", "talkpipe.app.chatterlang_script", "--load-module", "data/custom_module.py", "--script", "TALKPIPE_SCRIPT"]
