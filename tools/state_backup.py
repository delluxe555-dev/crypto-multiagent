#!/usr/bin/env python3
"""state_backup.py — runs/live durumunu GitHub'a yedekler ve geri yükler.

Render ücretsiz planında kalıcı disk yok: her deploy/restart konteyner diskini
siler. Bu araç durum dosyalarını (`triggers.json`, `telegram_state.json`,
`journal.jsonl`, son karar dosyaları) tek bir zip olarak **ayrı `state`
branch'ine** yazar; `main`'e dokunmaz (Render yeniden deploy olmasın).

    python tools/state_backup.py --pull     # konteyner açılışında: durumu geri yükle
    python tools/state_backup.py --push     # 5 dk'da bir: durumu yedekle
    python tools/state_backup.py --status   # son işlem bilgisi

Ortam değişkenleri:
    GH_STATE_TOKEN   zorunlu (fine-grained PAT, Contents: Read/Write)
    GH_STATE_REPO    varsayılan delluxe555-dev/crypto-multiagent
    GH_STATE_BRANCH  varsayılan state
    LIVE_DIR         varsayılan <repo>/runs/live

Token yoksa komut sessizce 0 ile çıkar (bot çalışmaya devam eder).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live")

REPO = os.environ.get("GH_STATE_REPO") or "delluxe555-dev/crypto-multiagent"
BRANCH = os.environ.get("GH_STATE_BRANCH") or "state"
TOKEN = (os.environ.get("GH_STATE_TOKEN") or "").strip()
META = Path(os.environ.get("STATE_BACKUP_META") or ROOT / "runs" / "state_backup.json")

API = "https://api.github.com"
ZIP_NAME = "state.zip"
# Karar dosyaları: bundan eski olanları yedeğe koyma (tazeleme zaten üretir).
DECISION_MAX_AGE_H = float(os.environ.get("STATE_DECISION_MAX_AGE_H") or 6)
MAX_FILE = int(os.environ.get("STATE_MAX_FILE_BYTES") or 2 * 1024 * 1024)
# journal.jsonl büyürse son bu kadar satırı sakla.
JOURNAL_KEEP_LINES = int(os.environ.get("STATE_JOURNAL_KEEP_LINES") or 2000)


# ------------------------------------------------------------------ yardımcı
def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _meta() -> dict:
    try:
        return json.loads(META.read_text("utf-8"))
    except Exception:
        return {}


def _save_meta(patch: dict) -> None:
    m = _meta()
    m.update(patch)
    m["at"] = _now()
    try:
        META.parent.mkdir(parents=True, exist_ok=True)
        tmp = META.with_suffix(".tmp")
        tmp.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(META)
    except Exception as exc:
        print(f"meta yazılamadı: {exc}", flush=True)


def _api(method: str, path: str, payload: dict | None = None) -> dict:
    url = f"{API}{path}"
    body = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "crypto-multiagent-state-backup")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8")
    return json.loads(raw) if raw.strip() else {}


def _api_status(exc: urllib.error.HTTPError) -> int:
    return int(getattr(exc, "code", 0) or 0)


# --------------------------------------------------------------------- zip
def _journal_bytes(p: Path) -> bytes | None:
    try:
        if p.stat().st_size <= MAX_FILE:
            return p.read_bytes()
        lines = p.read_text("utf-8", errors="replace").splitlines()[-JOURNAL_KEEP_LINES:]
        return ("\n".join(lines) + "\n").encode("utf-8")
    except Exception:
        return None


def build_zip() -> bytes:
    """runs/live içinden yedeğe değer dosyaları topla."""
    buf = io.BytesIO()
    cutoff = time.time() - DECISION_MAX_AGE_H * 3600
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in ("triggers.json", "telegram_state.json"):
            p = LIVE / name
            try:
                if p.is_file() and p.stat().st_size <= MAX_FILE:
                    z.writestr(name, p.read_bytes())
            except OSError:
                continue
        j = _journal_bytes(LIVE / "journal.jsonl")
        if j:
            z.writestr("journal.jsonl", j)
        for p in sorted(LIVE.glob("*/decision_*.json")):
            try:
                st = p.stat()
            except OSError:
                continue
            if st.st_mtime < cutoff or st.st_size > MAX_FILE:
                continue
            try:
                z.writestr(p.relative_to(LIVE).as_posix(), p.read_bytes())
            except OSError:
                continue
    return buf.getvalue()


def _remote_zip() -> bytes | None:
    """state branch'indeki son zip'i indir; branch/yoksa None."""
    try:
        ref = _api("GET", f"/repos/{REPO}/git/ref/heads/{BRANCH}")
    except urllib.error.HTTPError as exc:
        if _api_status(exc) == 404:
            return None
        raise
    sha = ((ref.get("object") or {}).get("sha") or "").strip()
    if not sha:
        return None
    tree = _api("GET", f"/repos/{REPO}/git/trees/{sha}?recursive=1")
    blob_sha = None
    for item in tree.get("tree") or []:
        if item.get("path") == ZIP_NAME and item.get("type") == "blob":
            blob_sha = item.get("sha")
            break
    if not blob_sha:
        return None
    blob = _api("GET", f"/repos/{REPO}/git/blobs/{blob_sha}")
    data = base64.b64decode(blob.get("content") or "")
    return data or None


def _checked_at(state_bytes: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(state_bytes)) as z:
            if "triggers.json" in z.namelist():
                return json.loads(z.read("triggers.json").decode("utf-8")).get("checked_at") or ""
    except Exception:
        pass
    return ""


def restore(state_bytes: bytes, force: bool = False) -> dict:
    """zip'i LIVE dizinine aç. Yerel durum daha yeniyse dokunma."""
    remote_at = _checked_at(state_bytes)
    local_at = ""
    lp = LIVE / "triggers.json"
    try:
        if lp.is_file():
            local_at = json.loads(lp.read_text("utf-8")).get("checked_at") or ""
    except Exception:
        local_at = ""
    if not force and local_at and remote_at and remote_at <= local_at:
        return {"restored": False, "reason": "yerel durum daha yeni",
                "local": local_at, "remote": remote_at}

    LIVE.mkdir(parents=True, exist_ok=True)
    root = LIVE.resolve()
    written = 0
    with zipfile.ZipFile(io.BytesIO(state_bytes)) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            target = (LIVE / info.filename).resolve()
            # path traversal koruması
            if root not in target.parents and target != root:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(target.suffix + ".restore")
            tmp.write_bytes(z.read(info))
            tmp.replace(target)
            written += 1
    return {"restored": True, "files": written, "remote": remote_at}


# -------------------------------------------------------------------- push
def push(force: bool = False) -> dict:
    if not LIVE.is_dir():
        return {"pushed": False, "reason": "LIVE dizini yok"}
    data = build_zip()
    if not data:
        return {"pushed": False, "reason": "yedeğe dosya yok"}
    digest = hashlib.sha256(data).hexdigest()
    meta = _meta()
    if not force and digest == meta.get("last_hash"):
        return {"pushed": False, "reason": "değişiklik yok", "sha256": digest[:12]}

    blob = _api("POST", f"/repos/{REPO}/git/blobs",
                {"content": base64.b64encode(data).decode(), "encoding": "base64"})
    tree = _api("POST", f"/repos/{REPO}/git/trees",
                {"tree": [{"path": ZIP_NAME, "mode": "100644", "type": "blob",
                           "sha": blob["sha"]}]})
    commit = _api("POST", f"/repos/{REPO}/git/commits",
                  {"message": f"state: {_now()} ({len(data)} B)",
                   "tree": tree["sha"], "parents": []})
    sha = commit["sha"]
    try:
        _api("PATCH", f"/repos/{REPO}/git/refs/heads/{BRANCH}",
             {"sha": sha, "force": True})
    except urllib.error.HTTPError as exc:
        if _api_status(exc) != 404:
            raise
        _api("POST", f"/repos/{REPO}/git/refs",
             {"ref": f"refs/heads/{BRANCH}", "sha": sha})

    _save_meta({"last_hash": digest, "last_push_at": _now(), "last_commit": sha,
                "last_bytes": len(data), "repo": REPO, "branch": BRANCH,
                "last_push_ok": True, "last_push_error": None})
    return {"pushed": True, "commit": sha[:12], "bytes": len(data),
            "sha256": digest[:12]}


# --------------------------------------------------------------------- ana
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="runs/live durumunu GitHub'a yedekle")
    ap.add_argument("--pull", action="store_true", help="açılışta durumu geri yükle")
    ap.add_argument("--push", action="store_true", help="durumu yedekle")
    ap.add_argument("--status", action="store_true", help="son işlem bilgisi")
    ap.add_argument("--force", action="store_true", help="hash/yaş kontrollerini atla")
    a = ap.parse_args(argv)

    if a.status:
        m = _meta()
        print(json.dumps({"token": bool(TOKEN), "repo": REPO, "branch": BRANCH,
                          "live": str(LIVE), **m}, ensure_ascii=False, indent=1))
        return 0

    if not TOKEN:
        # token yoksa bot normal çalışsın; her turda gürültü yapma
        if a.pull:
            print("state_backup: GH_STATE_TOKEN yok, geri yükleme atlandı", flush=True)
        return 0

    try:
        if a.pull:
            data = _remote_zip()
            if not data:
                print("state_backup: uzak durum yok (ilk çalıştırma)", flush=True)
                _save_meta({"last_pull_at": _now(), "last_pull_ok": True,
                            "last_pull_result": "uzak durum yok"})
                return 0
            res = restore(data, force=a.force)
            print(f"state_backup: geri yükleme {res}", flush=True)
            _save_meta({"last_pull_at": _now(), "last_pull_ok": True,
                        "last_pull_result": res, "repo": REPO, "branch": BRANCH})
            return 0

        if a.push:
            res = push(force=a.force)
            print(f"state_backup: yedekleme {res}", flush=True)
            if not res.get("pushed"):
                _save_meta({"last_push_ok": True, "last_push_result": res})
            return 0
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:300]
        except Exception:
            pass
        err = f"HTTP {exc.code}: {detail or exc.reason}"
        print(f"state_backup HATA: {err}", flush=True)
        _save_meta({("last_pull_ok" if a.pull else "last_push_ok"): False,
                    ("last_pull_error" if a.pull else "last_push_error"): err})
        return 1
    except Exception as exc:
        print(f"state_backup HATA: {type(exc).__name__}: {exc}", flush=True)
        _save_meta({("last_pull_ok" if a.pull else "last_push_ok"): False,
                    ("last_pull_error" if a.pull else "last_push_error"): str(exc)})
        return 1

    ap.print_help()
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
