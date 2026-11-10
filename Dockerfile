FROM python:3.11-slim

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y --no-install-recommends bash && rm -rf /var/lib/apt/lists/* && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir fastapi "uvicorn[standard]" requests python-dotenv pandas numpy websocket-client urllib3

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Railway kalici diskleri buraya baglanir (yoksa da calisir).
RUN mkdir -p /app/runs/live /app/cache/alertachart

# scan ve trigger_watch kendi kendini toparlar: surec olurse 5 sn sonra yeniden baslar.
# state_backup: GH_STATE_TOKEN varsa GitHub'dan durumu geri yukler; yoksa sessizce atlar
# (Railway'de kalici disk kullanildigi icin token gerekmez).
CMD ["sh", "-c", "python3 -u tools/state_backup.py --pull || true; python3 -u tools/update_universe.py & python3 -u tools/fetcher_render.py & (while true; do sleep 300; python3 -u tools/state_backup.py --push || true; done) & (while true; do python3 -u tools/scan.py --watch --interval 300 --auto; echo 'scan durdu, 5s sonra yeniden'; sleep 5; done) & (while true; do python3 -u tools/trigger_watch.py --watch --interval 60; echo 'trigger_watch durdu, 5s sonra yeniden'; sleep 5; done) & python3 -m uvicorn tools.upload_payload:app --host 0.0.0.0 --port ${PORT:-8000}"]
