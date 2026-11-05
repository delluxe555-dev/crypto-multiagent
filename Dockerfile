FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi "uvicorn[standard]" requests python-dotenv pandas numpy websocket-client urllib3

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["sh", "-c", "python3 -u tools/update_universe.py & python3 -u tools/fetcher_render.py & python3 -u tools/scan.py --watch --interval 300 --auto & python3 -u tools/trigger_watch.py --watch --interval 60 & python3 -m uvicorn tools.upload_payload:app --host 0.0.0.0 --port ${PORT:-8000}"]
