FROM python:3.10

RUN pip install --upgrade pip

WORKDIR /scripts

COPY requirements.txt /scripts/
COPY prune.sh /scripts/
COPY generate_pruning_lists.py /scripts/
COPY get_pipelines.py /scripts/

RUN pip install -r requirements.txt

ENTRYPOINT ["/bin/bash", "/scripts/prune.sh"]
