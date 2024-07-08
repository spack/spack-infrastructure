FROM python:3

WORKDIR /scripts
COPY requirements.txt ./
RUN pip install --upgrade -r requirements.txt
COPY cache_indexer.py ./

ENTRYPOINT ["python", "./cache_indexer.py"]
