FROM python:3

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY cancel_and_restart_stuck_pipelines.py ./

ENTRYPOINT [ "python", "./cancel_and_restart_stuck_pipelines.py"]
