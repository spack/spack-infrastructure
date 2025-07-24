FROM python:3

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --upgrade uv
RUN uv pip install --system --no-cache-dir -r requirements.txt
COPY cancel_and_restart_stuck_pipelines.py ./

ENTRYPOINT [ "python", "./cancel_and_restart_stuck_pipelines.py"]
