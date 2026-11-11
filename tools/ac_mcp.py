#!/usr/bin/env python3
"""ac_mcp.py — AlertaChart uzak MCP'sine botun KENDI kimligiyle erisen ince istemci.

Neden: Railway AlertaChart MCP'sine ag olarak erisebiliyor (401 + WWW-Authenticate
donuyor). Erisim icin yalnizca botun kendi OAuth grant'i gerekiyor. Bu modul o
grant'i `_oauth.json` dosyasinda tutar, gerektiginde refresh eder ve **donen yeni
refresh token'i ayni dosyaya yazar** (rotation tek sahip kurali).

Token dosyasi (CA_AC_CACHE/_oauth.json):
    {"access": "...", "refresh": "...", "expires": <ms>,
     "metadata": {"client": {"client_id": "mcpc_..."}}}

Alternatif: AC_OAUTH_JSON ortam degiskeni ayni JSON'u tasir (salt okunur mod).

Kullanim:
    import ac_mcp
    if ac_mcp.available():
        ac_mcp.call("get_practice", {})
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MCP_URL = "https://www.alertachart.com/mcp"
TOKEN_URL = "https://www.alertachart.com/oauth/token"
RESOURCE = "https://www.alertachart.com/mcp"
UA = "crypto-multiagent/1.0"

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("CA_AC_CACHE") or ROOT / "cache" / "alertachart")
TOKEN_FILE = Path(os.environ.get("AC_OAUTH_FILE") or CACHE / "_oauth.json")

_lock = threading.RLock()
_client = None          # type: ignore[var-annotated]
_last_error = ""


def _now_ms() -> int:
    return int(time.time() * 1000)


def tokens_path() -> Path:
    return TOKEN_FILE


def load_tokens() -> dict:
    raw = (os.environ.get("AC_OAUTH_JSON") or "").strip()
    if raw:
        return json.loads(raw)
    if TOKEN_FILE.is_file():
        return json.loads(TOKEN_FILE.read_text("utf-8"))
    return {}


def save_tokens(data: dict) -> None:
    """Atomik yaz: yarim dosya kalirsa kimlik kaybolmasin."""
    if (os.environ.get("AC_OAUTH_JSON") or "").strip():
        return  # ortam degiskeni salt okunur
    try:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = TOKEN_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        os.replace(tmp, TOKEN_FILE)
    except Exception as exc:  # noqa: BLE001
        print(f"ac_mcp: token yazilamadi: {exc}", flush=True)


def _client_id(data: dict) -> str:
    cid = (((data.get("metadata") or {}).get("client") or {}).get("client_id")
           or data.get("client_id") or os.environ.get("AC_OAUTH_CLIENT_ID") or "")
    return str(cid).strip()


def available() -> bool:
    try:
        return bool(_client_id(load_tokens()) and load_tokens().get("refresh"))
    except Exception:
        return False


def _refresh(data: dict) -> str:
    """Refresh token ile yeni access token al; rotasyonu dosyaya yaz."""
    cid = _client_id(data)
    if not cid:
        raise RuntimeError("client_id yok")
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": data["refresh"],
        "client_id": cid,
        "resource": RESOURCE,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        tok = json.loads(r.read().decode("utf-8", "replace"))
    data["access"] = tok["access_token"]
    if tok.get("refresh_token"):
        data["refresh"] = tok["refresh_token"]
    data["expires"] = _now_ms() + int(tok.get("expires_in") or 3600) * 1000
    meta = data.setdefault("metadata", {})
    meta.setdefault("client", {})["client_id"] = cid
    meta["tokenType"] = tok.get("token_type") or "Bearer"
    if tok.get("scope"):
        meta["scope"] = tok["scope"]
    save_tokens(data)
    return data["access"]


def access_token(margin_s: int = 120) -> str:
    data = load_tokens()
    if not data.get("refresh"):
        raise RuntimeError("AlertaChart OAuth kimligi yok")
    if data.get("access") and _now_ms() < int(data.get("expires") or 0) - margin_s * 1000:
        return data["access"]
    return _refresh(data)


class _MCP:
    """Tek oturum: initialize + tools/call (streamable HTTP, SSE veya JSON)."""

    def __init__(self, access: str, url: str = MCP_URL):
        self.url = url
        self.h = {
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": UA,
        }
        self.n = 0
        self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "crypto-multiagent", "version": "1.0"}}})
        self.n = 1
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _post(self, body: dict) -> dict | None:
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(),
                                     method="POST", headers=self.h)
        with urllib.request.urlopen(req, timeout=45) as r:
            raw = r.read().decode("utf-8", "replace")
            sid = r.headers.get("mcp-session-id")
        if sid:
            self.h["Mcp-Session-Id"] = sid
        if not raw.strip():
            return None
        if raw.lstrip().startswith(("event:", "data:")):
            chunks = [ln[5:].strip() for ln in raw.splitlines() if ln.startswith("data:")]
            raw = chunks[-1] if chunks else raw
        return json.loads(raw)

    def call(self, name: str, args: dict) -> dict:
        self.n += 1
        res = self._post({"jsonrpc": "2.0", "id": self.n, "method": "tools/call",
                          "params": {"name": name, "arguments": args}}) or {}
        if res.get("error"):
            raise RuntimeError(f"{name}: {res['error']}")
        r = res.get("result") or {}
        content = r.get("content") or []
        txt = content[0].get("text", "") if content else ""
        if r.get("isError"):
            raise RuntimeError(f"{name}: {txt[:300]}")
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            return {"_text": txt}


def reset() -> None:
    """Oturumu dusur (401/ag hatasindan sonra)."""
    global _client
    with _lock:
        _client = None


def call(name: str, args: dict | None = None, retry: bool = True) -> dict:
    """MCP aracini cagir. 401/oturum hatasinda tokeni yenileyip bir kez tekrar dener."""
    global _client, _last_error
    with _lock:
        try:
            if _client is None:
                _client = _MCP(access_token())
            return _client.call(name, args or {})
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace")[:200]
            except Exception:
                pass
            _last_error = f"HTTP {exc.code}: {detail}"
            reset()
            if retry and exc.code in (401, 403, 400):
                # access token bayat olabilir: zorla refresh + yeni oturum
                try:
                    data = load_tokens()
                    data["expires"] = 0
                    _refresh(data)
                except Exception as rexc:  # noqa: BLE001
                    _last_error = f"{_last_error} | refresh: {rexc}"
                    raise RuntimeError(_last_error) from rexc
                return call(name, args, retry=False)
            raise RuntimeError(_last_error) from exc
        except Exception as exc:  # noqa: BLE001
            _last_error = f"{type(exc).__name__}: {exc}"[:240]
            reset()
            raise


def last_error() -> str:
    return _last_error


def probe() -> dict:
    """Kimlik + baglanti kontrolu: get_practice hesabini okur."""
    try:
        p = call("get_practice", {})
        accs = p.get("accounts") or []
        a = next((x for x in accs if x.get("default")), accs[0] if accs else {})
        return {"ok": True, "account": a.get("name"), "balance": a.get("balance"),
                "positions": len(a.get("positions") or []),
                "pending": len(a.get("pending_orders") or [])}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:240],
                "available": available(), "last_error": last_error()}
