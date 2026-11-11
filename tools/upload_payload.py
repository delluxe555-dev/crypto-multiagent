#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Query, Request

app = FastAPI(title="AlertaChart Payload Upload")
ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("CA_AC_CACHE") or ROOT / "cache" / "alertachart")
LIVE_DIR = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live")
# Varsayılan token gömülü: yeni sunucuda (Railway) hiçbir ortam değişkeni
# girmeden çalışsın. PAYLOAD_UPLOAD_TOKEN verilirse o kullanılır.
DEFAULT_TOKEN = "mG4Y9N1LPe6Sgc2MuZb0HVIDn5JTAkvqoUayrx7Wl8FQ3iws"
TOKEN = (os.environ.get("PAYLOAD_UPLOAD_TOKEN") or DEFAULT_TOKEN).strip()


def _apply_payload():
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "tools" / "apply_payload.py")],
            cwd=str(ROOT),
            timeout=180,
        )
    except Exception as e:
        print(f"apply_payload error: {e}", flush=True)


def _commit() -> str:
    for key in ("RAILWAY_GIT_COMMIT_SHA", "RENDER_GIT_COMMIT", "GIT_COMMIT",
                "SOURCE_COMMIT", "RAILWAY_GIT_COMMIT"):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val[:12]
    return ""


def _paper_line() -> str:
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import paper  # noqa: WPS433
        paper.configure(LIVE_DIR)
        return paper.summary_line()
    except Exception as exc:
        return f"paper yok: {type(exc).__name__}"


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    return {
        "ok": True,
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "commit": _commit(),
        "paper": _paper_line(),
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
    live = LIVE_DIR
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
    p = LIVE_DIR / "triggers.json"
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


def _gh_probe() -> dict:
    """Render'daki GH_STATE_TOKEN'ın kimliğini ve repo izinlerini göster."""
    tok = (os.environ.get("GH_STATE_TOKEN") or "").strip()
    repo = os.environ.get("GH_STATE_REPO") or "delluxe555-dev/crypto-multiagent"
    if not tok:
        return {"ok": False, "error": "GH_STATE_TOKEN yok"}

    def call(path: str) -> dict:
        req = urllib.request.Request(f"https://api.github.com{path}")
        req.add_header("Authorization", f"Bearer {tok}")
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        req.add_header("User-Agent", "crypto-multiagent-state-backup")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.loads(r.read().decode() or "{}")
                return {"status": r.status, "scopes": r.headers.get("X-OAuth-Scopes"), "body": body}
        except urllib.error.HTTPError as e:
            try:
                detail = e.read().decode()[:300]
            except Exception:
                detail = ""
            return {"status": e.code, "error": detail or str(e.reason)}
        except Exception as e:
            return {"status": None, "error": f"{type(e).__name__}: {e}"}

    u = call("/user")
    ub = u.get("body") or {}
    r = call(f"/repos/{repo}")
    rb = r.get("body") or {}
    ref = call(f"/repos/{repo}/git/ref/heads/{os.environ.get('GH_STATE_BRANCH') or 'state'}")
    return {
        "token_prefix": tok[:11] + "..." if tok else "",
        "token_length": len(tok),
        "token_type": "fine-grained" if tok.startswith("github_pat_") else
                      "classic/other" if tok.startswith("ghp_") else "bilinmiyor",
        "user": {"status": u.get("status"), "login": ub.get("login"),
                 "scopes": u.get("scopes"), "error": u.get("error")},
        "repo": {"status": r.get("status"), "full_name": rb.get("full_name"),
                 "private": rb.get("private"), "permissions": rb.get("permissions"),
                 "scopes": r.get("scopes"), "error": r.get("error")},
        "state_branch": {"status": ref.get("status"),
                         "sha": ((ref.get("body") or {}).get("object") or {}).get("sha"),
                         "error": ref.get("error")},
    }


@app.get("/debug/state")
def debug_state(token: str = Query(default=""), probe: int = Query(default=0, ge=0, le=1)):
    """GitHub durum yedeklemesi: token var mı, son push/pull ne oldu."""
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    meta_path = Path(os.environ.get("STATE_BACKUP_META") or ROOT / "runs" / "state_backup.json")
    info = {
        "token_present": bool((os.environ.get("GH_STATE_TOKEN") or "").strip()),
        "repo": os.environ.get("GH_STATE_REPO") or "delluxe555-dev/crypto-multiagent",
        "branch": os.environ.get("GH_STATE_BRANCH") or "state",
        "live_dir": str(LIVE_DIR),
        "live_exists": LIVE_DIR.is_dir(),
    }
    try:
        info["meta"] = json.loads(meta_path.read_text("utf-8"))
    except Exception as exc:
        info["meta"] = None
        info["meta_error"] = str(exc)
    for name in ("triggers.json", "telegram_state.json", "journal.jsonl", "paper.json"):
        p = LIVE_DIR / name
        info[name] = {"exists": p.is_file(),
                      "bytes": p.stat().st_size if p.is_file() else 0}
    if probe:
        info["probe"] = _gh_probe()
    return {"ok": True, "state": info}


@app.get("/debug/selftest")
def debug_selftest(token: str = Query(default="")):
    """Borsa/veri erişimi ve süreç sağlığı: Binance, overlay cache, tetik izleyici."""
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    out: dict = {"ok": True, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    # 1) Mum verisi kaynaklari (scan/trigger_watch'in canli veri kaynagi)
    try:
        sys.path.insert(0, str(ROOT / "dataflows"))
        import binance as bn  # noqa: WPS433
        sources: dict = {}
        for name, fn in bn._FETCHERS.items():
            t0 = time.time()
            try:
                rows = fn("BTCUSDT", "5m", 2, "perp")
                sources[name] = {"ok": bool(rows),
                                 "close": rows[-1]["close"] if rows else None,
                                 "latency_ms": int((time.time() - t0) * 1000)}
            except Exception as exc:
                sources[name] = {"ok": False,
                                 "error": f"{type(exc).__name__}: {exc}"[:160],
                                 "latency_ms": int((time.time() - t0) * 1000)}
        rows = bn.get_klines("BTCUSDT", "5m", 2, "perp")
        out["sources"] = sources
        out["klines"] = {"used": bn.LAST_SOURCE or None,
                         "close": rows[-1]["close"] if rows else None,
                         "open_time": rows[-1]["open_time"] if rows else None}
    except Exception as exc:
        out["sources"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}

    # 2) overlay cache
    try:
        syms = sorted(p.name for p in CACHE.iterdir() if p.is_dir()) if CACHE.is_dir() else []
        pl = CACHE / "_payload.json"
        out["overlay"] = {"symbol_dirs": len(syms), "payload_exists": pl.is_file(),
                          "payload_age_min": round((time.time() - pl.stat().st_mtime) / 60, 1)
                          if pl.is_file() else None}
    except Exception as exc:
        out["overlay"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}

    # 3) süreçler: trigger_watch son kontrolü + kasa
    try:
        tp = LIVE_DIR / "triggers.json"
        data = json.loads(tp.read_text("utf-8")) if tp.is_file() else {}
        out["trigger_watch"] = {"checked_at": data.get("checked_at"),
                                "open": len([x for x in (data.get("positions") or {}).values()
                                             if x.get("status") == "open"])}
    except Exception as exc:
        out["trigger_watch"] = {"error": f"{type(exc).__name__}: {exc}"[:200]}
    out["paper"] = _paper_line()
    return out


@app.get("/debug/paper")
def debug_paper(token: str = Query(default="")):
    """Kağıt hesap: bakiye, K/Z, açık pozisyonlar, son işlemler."""
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import paper  # noqa: WPS433
        paper.configure(LIVE_DIR)
        return {"ok": True, "paper": paper.summary()}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


@app.get("/debug/mcp-probe")
def debug_mcp_probe(token: str = Query(default="")):
    """Railway'den AlertaChart MCP'sine ag erisimi var mi? (OAuth denemez.)"""
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    url = "https://www.alertachart.com/mcp"
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "probe", "version": "1"}}}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "User-Agent": "crypto-multiagent/1.0"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return {"ok": True, "status": r.status, "ms": int((time.time() - t0) * 1000),
                    "www_authenticate": r.headers.get("WWW-Authenticate")}
    except urllib.error.HTTPError as e:
        return {"ok": True, "reachable": True, "status": e.code,
                "ms": int((time.time() - t0) * 1000),
                "www_authenticate": e.headers.get("WWW-Authenticate"),
                "body": e.read().decode("utf-8", "replace")[:200]}
    except Exception as exc:
        return {"ok": False, "reachable": False, "error": f"{type(exc).__name__}: {exc}"[:200],
                "ms": int((time.time() - t0) * 1000)}


@app.post("/admin/oauth")
async def admin_oauth(request: Request, x_upload_token: str = Header(default="")):
    """Botun AlertaChart OAuth kimligini (refresh token) sakla.

    Govde: {"refresh": "...", "client_id": "mcpc_...", "access": "...", "expires": 0}
    veya dogrudan token ucu yaniti. Dosya CA_AC_CACHE/_oauth.json'a atomik yazilir.
    """
    if not TOKEN or x_upload_token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        data = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad json: {e}")
    if not isinstance(data, dict) or not data.get("refresh"):
        raise HTTPException(status_code=400, detail="refresh gerekli")
    cid = str(data.get("client_id") or "").strip()
    meta = data.setdefault("metadata", {})
    if cid:
        meta.setdefault("client", {})["client_id"] = cid
    CACHE.mkdir(parents=True, exist_ok=True)
    p = CACHE / "_oauth.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, p)
    try:
        os.chmod(p, 0o600)
    except Exception:
        pass
    return {"ok": True, "path": str(p), "client_id": (meta.get("client") or {}).get("client_id")}


@app.get("/debug/loop")
def debug_loop(token: str = Query(default="")):
    """mcp_loop kalp atisi: veri tazeleme dongusu canli mi, en son ne yapti."""
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    out = {"ok": True}
    try:
        p = LIVE_DIR / "mcp_loop.json"
        out["beat"] = json.loads(p.read_text("utf-8")) if p.is_file() else None
        if p.is_file():
            out["beat_age_min"] = round(
                (time.time() - p.stat().st_mtime) / 60, 1)
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    cache = Path(os.environ.get("CA_AC_CACHE") or CACHE)
    for name in ("_payload.json", "_extras.json", "_market.json", "_oauth.json"):
        f = cache / name
        out[name] = round((time.time() - f.stat().st_mtime) / 60, 1) if f.is_file() else None
    return out


@app.get("/debug/practice")
def debug_practice(token: str = Query(default="")):
    """Alerta Practice hesabi + aynalama durumu."""
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import ac_mcp  # noqa: WPS433
        import practice_bridge as pb  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    out = {"ok": True, "enabled": pb.enabled(), "available": ac_mcp.available(),
           "token_file": str(ac_mcp.tokens_path())}
    if out["available"]:
        out.update(ac_mcp.probe())
        try:
            tp = LIVE_DIR / "triggers.json"
            data = json.loads(tp.read_text("utf-8")) if tp.is_file() else {}
            pos = [p for p in (data.get("positions") or {}).values() if p.get("status") == "open"]
            out["mirrored"] = sum(1 for p in pos if p.get("practice"))
            out["pending"] = sum(1 for p in pos if not p.get("practice"))
            out["errors"] = [{"s": p.get("symbol"), "e": p.get("practice_error") or
                              (p.get("practice") or {}).get("close_error")}
                             for p in pos if p.get("practice_error") or
                             (p.get("practice") or {}).get("close_error")]
        except Exception as exc:  # noqa: BLE001
            out["positions_error"] = f"{type(exc).__name__}: {exc}"
    try:
        lp = LIVE_DIR / "practice.log"
        if lp.is_file():
            out["log"] = lp.read_text("utf-8", "replace").splitlines()[-25:]
    except Exception:
        pass
    return out


@app.post("/debug/practice-test")
def debug_practice_test(x_upload_token: str = Header(default=""),
                        notional: float = Query(default=20.0, ge=5, le=500)):
    """Kucuk bir market emri ac + hemen kapat: aynalama yolunu uctan uca dogrular."""
    if not TOKEN or x_upload_token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import ac_mcp  # noqa: WPS433
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    out = {"ok": True}
    try:
        out["place"] = ac_mcp.call("place_practice_order", {
            "symbol": "BTCUSDT.P", "market": "perp", "side": "long", "type": "market",
            "notional_usd": notional, "leverage": 1})
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "step": "place", "error": f"{type(exc).__name__}: {exc}"[:300]}
    try:
        out["close"] = ac_mcp.call("close_practice_position",
                                   {"symbol": "BTCUSDT.P", "market": "perp", "fraction": 1})
    except Exception as exc:  # noqa: BLE001
        out["close_error"] = f"{type(exc).__name__}: {exc}"[:300]
    try:
        out["probe"] = ac_mcp.probe()
    except Exception:
        pass
    return out


@app.get("/debug/extras")
def debug_extras(token: str = Query(default=""), keys: str = Query(default="")):
    """Piyasa-ustu katman (`_extras.json`): tazelik + istenen katmanlar."""
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    p = CACHE / "_extras.json"
    if not p.is_file():
        return {"ok": False, "error": "extras yok"}
    try:
        d = json.loads(p.read_text("utf-8"))
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    want = [k.strip() for k in keys.split(",") if k.strip()]
    body = {k: d.get(k) for k in want} if want else d
    return {"ok": True, "age_min": round((time.time() - p.stat().st_mtime) / 60, 1),
            "asof": d.get("asof"), "keys": sorted(k for k in d if k != "asof"),
            "extras": body}


@app.post("/debug/paper/reset")
def debug_paper_reset(token: str = Query(default=""), start: float = Query(default=0.0),
                      close_positions: int = Query(default=1, ge=0, le=1)):
    """Kağıt hesabı sıfırla (varsayılan PAPER_START_BALANCE).

    Açık takip pozisyonları sessizce `reset` durumuna alınır; böylece sıfırlama
    sonrası eski (hatalı girişli) pozisyonlar için TP/SL mesajı gitmez.
    """
    if not TOKEN or token != TOKEN:
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        import paper  # noqa: WPS433
        paper.configure(LIVE_DIR)
        res = paper.reset(start or None)
        closed = 0
        if close_positions:
            p = LIVE_DIR / "triggers.json"
            if p.is_file():
                try:
                    st = json.loads(p.read_text("utf-8"))
                except Exception:
                    st = {}
                now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for pos in (st.get("positions") or {}).values():
                    if pos.get("status") == "open":
                        pos["status"] = "reset"
                        pos["closed_at"] = now
                        pos["close_price"] = pos.get("entry")
                        pos["pending"] = []
                        closed += 1
                tmp = p.with_suffix(f".{os.getpid()}.tmp")
                tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")
                tmp.replace(p)
        return {"ok": True, "paper": res, "closed_positions": closed}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


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
            info["universe"] = parsed
        else:
            info["universe_path"] = str(uni)
            info["universe_exists"] = False
    return {"ok": True, "cache": info}
