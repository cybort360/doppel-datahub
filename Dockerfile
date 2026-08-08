FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt ./
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    /root/.local/bin/uv pip install --system --no-cache -r requirements.txt && \
    apt-get purge -y curl ca-certificates && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
COPY app ./app
COPY data ./data
COPY skills ./skills
COPY artifacts ./artifacts

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
