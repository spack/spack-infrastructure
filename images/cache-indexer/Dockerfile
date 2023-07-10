FROM python:3

WORKDIR /scripts
RUN pip install --upgrade boto3
COPY cache_indexer.py ./

ENTRYPOINT ["python", "./cache_indexer.py"]
