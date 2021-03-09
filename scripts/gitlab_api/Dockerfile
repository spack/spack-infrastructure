FROM python:3

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY gitlab_api.py ./

ENTRYPOINT [ "python", "./gitlab_api.py"]
