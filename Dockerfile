FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Cloud Run injects $PORT; bind to it.
CMD exec uvicorn taixable_copilot.api.app:app --host 0.0.0.0 --port ${PORT}
