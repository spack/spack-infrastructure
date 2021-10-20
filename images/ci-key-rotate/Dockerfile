FROM python:3

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY rotate_gitlab_aws_access_keys.py ./

ENTRYPOINT [ "python", "./rotate_gitlab_aws_access_keys.py"]
