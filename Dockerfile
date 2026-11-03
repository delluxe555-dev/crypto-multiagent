FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi "uvicorn[standard]" requests python-dotenv pandas numpy websocket-client urllib3

ENV PYTHONUNBUFFERED=1

CMD bash -c "python -u tools/scan.py --watch --interval 300 --auto & python -u tools/trigger_watch.py --watch --interval 60 & python -m uvicorn tools.upload_payload:app --host 0.0.0.0 --port $PORT"
