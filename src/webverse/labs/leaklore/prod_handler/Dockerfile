FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    procps iproute2 net-tools bash ca-certificates \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY syscheck.sh /usr/local/bin/syscheck
RUN chmod +x /usr/local/bin/syscheck

COPY templates ./templates

# Flag location requirement
RUN mkdir -p /root
COPY flag.txt /root/flag.txt

EXPOSE 8000
CMD ["python", "main.py"]
