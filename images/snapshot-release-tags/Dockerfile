FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade uv
RUN uv pip install --system -r requirements.txt

COPY . .

ENTRYPOINT [ "python" ]
