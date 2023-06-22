FROM python:3

WORKDIR /scripts
RUN pip install --upgrade awscli
COPY cache_indexer.py ./

ENTRYPOINT ["python", "./cache_indexer.py"]
