FROM debian:trixie-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install the Debian system Python plus scipy/numpy/pandas from apt mirrors.
# Large scientific packages are slow/unreliable from PyPI in some environments,
# so we rely on Debian packages for those and pip for the rest.
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-scipy \
    python3-pandas \
    python3-numpy \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python3 -m pip install --break-system-packages --no-cache-dir --timeout 300 --retries 10 -r requirements.txt

COPY app ./app
COPY data ./data
COPY skills ./skills
COPY artifacts ./artifacts

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
