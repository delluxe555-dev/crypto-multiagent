#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request

app = FastAPI(title="AlertaChart Payload Upload")
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache" / "alertachart"
TOKEN = os.environ.get("PAYLOAD_UPLOAD_TOKEN", "")


def _apply_payload():
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "apply_payload.py")],
            cwd=str(ROOT),
            timeout=180,
        )
    except Exception as e:
        print(f"apply_payload error: {e}", flush=True)


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


@app.get("/")
def root():
    return {"ok": True, "service": "upload-payload"}


@app.post("/upload-payload")
async def upload(request: Request, x_upload_token: str = Header(default="")):
    if not TOKEN or x_upload_token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad json: {e}")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="payload must be object")

    CACHE.mkdir(parents=True, exist_ok=True)
    out = CACHE / "_payload.json"
    out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    t = threading.Thread(target=_apply_payload, daemon=True)
    t.start()

    return {"ok": True, "queued": True}


@app.get("/debug/decisions")
def debug_decisions(token: str = Query(default=""), n: int = Query(default=2, ge=1, le=10)):
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    live = ROOT / "runs" / "live"
    files = []
    if live.is_dir():
        files = sorted(live.rglob("decision_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for p in files[:n]:
        try:
            data = json.loads(p.read_text("utf-8"))
        except Exception as e:
            data = {"_error": str(e)}
        out.append({"path": str(p.relative_to(ROOT)), "decision": data})
    return {"ok": True, "count": len(out), "items": out}
