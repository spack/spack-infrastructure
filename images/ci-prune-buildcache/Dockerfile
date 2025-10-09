FROM python:3.13-slim

WORKDIR /app/

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY entrypoint.sh ./
COPY fetch_keeplist.py ./
COPY prune.py ./

WORKDIR /app/

ENTRYPOINT [ "bash", "/app/entrypoint.sh"]
