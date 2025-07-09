FROM python:3

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --upgrade uv
RUN uv pip install --system --no-cache-dir -r requirements.txt
COPY skipped_pipelines.py ./

ENTRYPOINT [ "python", "./skipped_pipelines.py"]
