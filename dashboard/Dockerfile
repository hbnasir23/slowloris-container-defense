FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir flask==3.0.3 requests==2.32.3
COPY app.py .
COPY templates ./templates
EXPOSE 8090
CMD ["python", "-u", "app.py"]
