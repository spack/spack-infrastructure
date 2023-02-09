FROM python:3.11-slim

WORKDIR /scripts/

COPY requirements.txt ./
COPY backup.py ./
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT [ "python", "./backup.py"]
