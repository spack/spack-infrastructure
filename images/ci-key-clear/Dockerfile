FROM python:3

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY delete_aws_admin_access_keys.py ./

ENTRYPOINT [ "python", "./delete_aws_admin_access_keys.py"]
