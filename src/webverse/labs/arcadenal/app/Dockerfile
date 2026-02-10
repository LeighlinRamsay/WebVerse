FROM python:3.12-slim

WORKDIR /app

# tiny utils for health + zipping
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server.py /app/server.py
COPY templates /app/templates
COPY static /app/static

EXPOSE 80
CMD ["python", "/app/server.py"]
