FROM python:3.10

WORKDIR /scripts/
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY SpackCIBridge.py ./

ENTRYPOINT [ "python", "./SpackCIBridge.py"]
