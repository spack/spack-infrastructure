# Note: this is the Dockerfile for the production image. The development image is located
# inside the dev/ subdirectory.

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/requirements.txt

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

COPY . .

RUN chmod +x ./entrypoint.sh
ENTRYPOINT [ "./entrypoint.sh" ]
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--access-logfile", "-", "analytics.wsgi"]
