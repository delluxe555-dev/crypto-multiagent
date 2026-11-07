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
    return {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "commit": (os.environ.get("RENDER_GIT_COMMIT") or os.environ.get("GIT_COMMIT") or "")[:12],
    }


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


@app.get("/debug/triggers")
def debug_triggers(token: str = Query(default=""), n: int = Query(default=20, ge=1, le=200)):
    """Tetik izleyicisinin durumu: acik pozisyonlar, son kapananlar, sinyal durumlari."""
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    p = ROOT / "runs" / "live" / "triggers.json"
    if not p.is_file():
        return {"ok": True, "exists": False, "open": [], "recent": [], "signals": {}}
    try:
        data = json.loads(p.read_text("utf-8"))
    except Exception as e:
        return {"ok": False, "error": str(e)}
    positions = list((data.get("positions") or {}).values())
    positions.sort(key=lambda x: x.get("opened_at") or "", reverse=True)
    sigs = list((data.get("signals") or {}).items())[-n:]
    return {
        "ok": True,
        "exists": True,
        "checked_at": data.get("checked_at"),
        "open": [x for x in positions if x.get("status") == "open"],
        "recent": positions[:n],
        "signals": dict(sigs),
    }


@app.get("/debug/cache")
def debug_cache(token: str = Query(default=""), symbol: str = Query(default="")):
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    ac = CACHE
    info = {"cache_dir": str(ac), "exists": ac.is_dir()}
    if symbol:
        d = ac / symbol / "15m"
        overlays = []
        if d.is_dir():
            for p in sorted(d.glob("overlay_*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                try:
                    o = json.loads(p.read_text("utf-8"))
                except Exception:
                    o = {}
                overlays.append({"file": p.name, "bar": o.get("bar"), "asof": o.get("asof"), "w": len(o.get("w") or []), "lab": len(o.get("lab") or [])})
        info["symbol"] = symbol
        info["overlays"] = overlays
    else:
        # summary: how many symbol dirs, recent payload
        syms = [p.name for p in ac.iterdir() if p.is_dir()] if ac.is_dir() else []
        payload = ac / "_payload.json"
        info["symbol_dirs"] = len(syms)
        info["sample_symbols"] = sorted(syms)[:15]
        info["payload_exists"] = payload.is_file()
        if payload.is_file():
            info["payload_mtime"] = datetime.fromtimestamp(payload.stat().st_mtime, timezone.utc).isoformat()
            try:
                pj = json.loads(payload.read_text("utf-8"))
                info["payload_symbols"] = len((pj.get("symbols") or {}))
                info["payload_symbol_names"] = sorted((pj.get("symbols") or {}).keys())[:20]
            except Exception:
                pass
        # universe debug
        uni = ROOT / "config" / "universe.txt"
        if uni.is_file():
            lines = uni.read_text("utf-8").splitlines()
            parsed = [l.strip() for l in lines if l.strip() and not l.strip().startswith("#")]
            info["universe_path"] = str(uni)
            info["universe_count"] = len(parsed)
            info["universe_sample"] = parsed[:15]
        else:
            info["universe_path"] = str(uni)
            info["universe_exists"] = False
    return {"ok": True, "cache": info}
