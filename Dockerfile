FROM python:3.11-slim AS builder
WORKDIR /app

# Tools to compile wheels when needed (kept only in builder)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
 && rm -rf /var/lib/apt/lists/*

# Generate requirements.txt from pyproject.toml using pip-tools
RUN pip install --no-cache-dir pip-tools
COPY pyproject.toml ./
RUN pip-compile --quiet --resolver=backtracking --strip-extras --output-file=requirements.txt pyproject.toml

FROM python:3.11-slim AS runtime
WORKDIR /app

# No system libs required for psycopg[binary]

# Install dependencies from generated requirements.txt
COPY --from=builder /app/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source code
COPY . .

ENV FLASK_APP=app:create_app
ENV FLASK_RUN_HOST=0.0.0.0
ENV HIGHLIGHTS_BASE_PATH=/data/highlights

EXPOSE 48138

CMD ["gunicorn", "-b", "0.0.0.0:48138", "app:create_app()"]
