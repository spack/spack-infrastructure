FROM python:3

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["/bin/bash"]
