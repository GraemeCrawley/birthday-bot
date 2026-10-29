FROM python:3.11-slim

WORKDIR /app

# Timezone comes from the TZ environment variable (set in .env); UTC if unset.
ENV TZ=UTC
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]
