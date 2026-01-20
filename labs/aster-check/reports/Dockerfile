FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Lab env vars ---
ENV COMPANY_NAME="AsterCheck Security" \
    DEV_ENDPOINT="http://canary-astercode-development.astercheck.local/" \
    APP_ENV="production" \
    VERSION="2.4.8" \
    SIGNING_KEY="REDACTED"

COPY . .
EXPOSE 8000
CMD ["python", "app.py"]