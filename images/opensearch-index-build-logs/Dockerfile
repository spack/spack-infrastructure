FROM python:3.10

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY build_logs_to_opensearch.py ./

ENTRYPOINT [ "python", "./build_logs_to_opensearch.py"]
