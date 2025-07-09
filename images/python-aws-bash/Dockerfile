FROM python:3

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --upgrade uv
RUN uv pip install --system --no-cache-dir -r requirements.txt

ENTRYPOINT ["/bin/bash"]
