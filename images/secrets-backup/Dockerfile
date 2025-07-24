FROM python:3.11-slim

WORKDIR /scripts/

COPY requirements.txt ./
COPY backup.py ./
RUN pip install --upgrade uv
RUN uv pip install --system --no-cache-dir -r requirements.txt

ENTRYPOINT [ "python", "./backup.py"]
