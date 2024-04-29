FROM python:3

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY delete_stale_branches.py ./

ENTRYPOINT [ "python", "./delete_stale_branches.py"]
