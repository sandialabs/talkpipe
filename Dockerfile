FROM python:3.11

WORKDIR /app

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
RUN pytest -m "not online" --log-cli-level=DEBUG
# RUN pip install -e .

# Install the basics of the scientific computing stack for analytics
RUN pip install numpy pandas matplotlib scikit-learn scipy

CMD ["python", "-m", "talkpipe.app.runscript", "--load_module", "data/custom_module.py", "--env", "TALKPIPE_SCRIPT"]
