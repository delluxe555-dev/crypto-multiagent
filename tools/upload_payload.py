#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request

app = FastAPI(title="AlertaChart Payload Upload")
ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "cache" / "alertachart"
TOKEN = os.environ.get("PAYLOAD_UPLOAD_TOKEN", "")

@app.get("/health")
def health():
    return {"ok": True, "ts": __import__("datetime").datetime.utcnow().isoformat() + "Z"}

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
    res = subprocess.run([sys.executable, str(ROOT / "tools" / "apply_payload.py")], cwd=str(ROOT))
    return {"ok": True, "returncode": res.returncode}
