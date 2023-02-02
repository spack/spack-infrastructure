FROM python:3.11-slim

WORKDIR /scripts/

# psycopg2 dependencies
RUN apt-get update && apt-get install -y libpq-dev gcc

COPY requirements.txt ./
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENTRYPOINT [ "python", "./build_logs_to_opensearch.py"]
