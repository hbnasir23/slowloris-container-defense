FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "locust==2.31.8" requests
COPY locustfile.py slow_benign.py ./
ENTRYPOINT []
