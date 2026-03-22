FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY static/ ./static/
COPY scripts/ ./scripts/

# Data and DB are mounted as volumes at runtime
RUN mkdir -p /data /audiobooks

ENV AUDIOBOOKS_PATH=/audiobooks
ENV METADATA_PATH=/data/metadata.json
ENV DB_PATH=/data/bookthing.db
ENV BASE_URL=http://localhost:8000

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
