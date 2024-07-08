FROM python:3.11

RUN apt-get update && apt-get install -y \
        gpg \
        gpg-agent && \
    apt-get autoremove --purge -y && \
    apt-get clean

COPY requirements.txt /srcs/requirements.txt

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /srcs/requirements.txt

COPY publish.py /srcs/publish.py
COPY validate_index.py /srcs/validate_index.py

WORKDIR /srcs
ENTRYPOINT ["python", "publish.py"]
