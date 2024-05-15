FROM python:3.10

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY sync-git-remotes.py ./

ENTRYPOINT [ "python", "./sync-git-remotes.py"]

