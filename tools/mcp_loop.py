#!/usr/bin/env python3
"""mcp_loop.py — botun KENDI AlertaChart kimligiyle veri tazeleme dongusu.

Railway artik AlertaChart MCP'sine erisebiliyor ve botun kendi OAuth grant'i var
(`/admin/oauth` ile yazilan `_oauth.json`). Bu dongu, asistan oturumuna ihtiyac
duymadan:

  * overlay'leri tazeler   (tools/mcp_refresh.py)  — varsayilan 120 dk
  * extras katmanini tazeler (tools/ac_extras.py)  — varsayilan 45 dk

Token yenileme tek yerde (ac_mcp) ve dosya kilidiyle yapilir: refresh token
rotasyonu iki surecte ayni anda calisirsa kimlik kaybolur.

    python tools/mcp_loop.py                # sonsuz dongu
    python tools/mcp_loop.py --once         # tek tur (test)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import ac_mcp  # noqa: E402
import mcp_refresh as mr  # noqa: E402


def _log(msg: str) -> None:
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    print(f"{ts} {msg}", flush=True)


LIVE = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live")
HEARTBEAT = LIVE / "mcp_loop.json"


def _beat(state: dict) -> None:
    """Dongunun canli oldugunu disariya goster (GET /debug/loop)."""
    try:
        LIVE.mkdir(parents=True, exist_ok=True)
        state = dict(state)
        state["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        tmp = HEARTBEAT.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, HEARTBEAT)
    except Exception:
        pass


def _env(token: str) -> dict:
    env = dict(os.environ)
    env["ALERTACHART_ACCESS_TOKEN"] = token
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run(args: list[str], token: str, timeout: int) -> int:
    try:
        p = subprocess.run([sys.executable, "-u"] + args, cwd=str(ROOT),
                           env=_env(token), timeout=timeout)
        return int(p.returncode)
    except subprocess.TimeoutExpired:
        _log(f"zaman asimi: {' '.join(args[:2])}")
        return 124
    except Exception as exc:  # noqa: BLE001
        _log(f"calistirilamadi {' '.join(args[:2])}: {exc}")
        return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--overlay-min", type=float,
                    default=float(os.environ.get("OVERLAY_REFRESH_MIN") or 120))
    ap.add_argument("--extras-min", type=float,
                    default=float(os.environ.get("EXTRAS_REFRESH_MIN") or 45))
    ap.add_argument("--batch", default=os.environ.get("OVERLAY_BATCH") or "13")
    ap.add_argument("--wait", default=os.environ.get("OVERLAY_WAIT") or "620")
    a = ap.parse_args(argv)

    port = os.environ.get("PORT") or "8000"
    url = os.environ.get("UPLOAD_URL") or f"http://127.0.0.1:{port}/upload-payload"
    up = (os.environ.get("PAYLOAD_UPLOAD_TOKEN") or mr.DEFAULT_UPLOAD_TOKEN).strip()

    last_ov = 0.0
    last_ex = 0.0

    cache = Path(os.environ.get("CA_AC_CACHE") or ROOT / "cache" / "alertachart")

    def _age_min(p: Path) -> float:
        try:
            return max(0.0, (time.time() - p.stat().st_mtime) / 60)
        except Exception:
            return 1e9

    # Yeniden baslatma firtinasi: veri zaten tazeyse hemen bastan baslama.
    age_ov = _age_min(cache / "_payload.json")
    age_ex = _age_min(cache / "_extras.json")
    if age_ov < a.overlay_min:
        last_ov = time.time() - (a.overlay_min - age_ov) * 60
    if age_ex < a.extras_min:
        last_ex = time.time() - (a.extras_min - age_ex) * 60
    _log(f"mcp_loop basladi · overlay {a.overlay_min:.0f} dk (yas {age_ov:.0f}) · "
         f"extras {a.extras_min:.0f} dk (yas {age_ex:.0f}) · upload {url}")
    _beat({"state": "started", "overlay_age_min": round(age_ov, 1),
           "extras_age_min": round(age_ex, 1), "overlay_every": a.overlay_min,
           "extras_every": a.extras_min})

    while True:
        if not ac_mcp.available():
            _log("AlertaChart kimligi yok (once /admin/oauth); 5 dk bekle")
            _beat({"state": "no-identity"})
            if a.once:
                return 1
            time.sleep(300)
            continue

        now = time.time()
        if now - last_ex >= a.extras_min * 60:
            try:
                token = ac_mcp.access_token()
            except Exception as exc:  # noqa: BLE001
                _log(f"token alinamadi: {exc}")
                token = ""
            if token:
                _log("extras tazeleniyor")
                _beat({"state": "extras-running"})
                rc = _run(["tools/ac_extras.py", "--upload-url", url,
                           "--upload-token", up], token, 2400)
                _log(f"extras bitti (rc {rc})")
                _beat({"state": "idle", "extras_rc": rc,
                       "extras_age_min": round(_age_min(cache / "_extras.json"), 1)})
            last_ex = time.time()

        if now - last_ov >= a.overlay_min * 60:
            try:
                token = ac_mcp.access_token()
            except Exception as exc:  # noqa: BLE001
                _log(f"token alinamadi: {exc}")
                token = ""
            if token:
                _log("overlay tazeleniyor")
                _beat({"state": "overlay-running"})
                rc = _run(["tools/mcp_refresh.py", "--batch", str(a.batch),
                           "--wait", str(a.wait), "--upload-url", url,
                           "--upload-token", up], token, 7200)
                _log(f"overlay bitti (rc {rc})")
                _beat({"state": "idle", "overlay_rc": rc,
                       "overlay_age_min": round(_age_min(cache / "_payload.json"), 1)})
            last_ov = time.time()

        if a.once:
            return 0
        time.sleep(60)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
