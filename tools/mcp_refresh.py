#!/usr/bin/env python3
"""mcp_refresh.py — AlertaChart uzak MCP'sinden 23 sembolluk overlay payload'u uretir.

Neden: Render AlertaChart MCP'sine erisemiyor; overlay'leri asistan/MCP dongusu
besliyor. Bu script o donguyu tek komuta indirir:

    python tools/mcp_refresh.py                    # 23 sembol, Render'a yukle
    python tools/mcp_refresh.py --local            # sadece cache'e yaz
    python tools/mcp_refresh.py --symbols BTCUSDT.P,ETHUSDT.P
    python tools/mcp_refresh.py --batch 18 --wait 600

Token: varsayilan olarak opencode kimlik deposundan okunur
(`~/.local/share/opencode/opencode.db`, credential tablosu). Suresi dolmussa
refresh_token ile yenilenir ve **yeni token ayni dosyaya geri yazilir** (refresh
token donduruldugu icin tek sahip kurali sart). Alternatif:

    --oauth-file C:\\path\\oauth.json     # {"access": "...", "refresh": "...", "expires": ms, ...}
    ALERTACHART_ACCESS_TOKEN=...         # yalniz erisim tokeni (yenileme yok)

Ortam: PAYLOAD_UPLOAD_TOKEN (Render upload), UPLOAD_URL.
Rate limit: get_orderflow 20 cagri / 10 dk. Bu yuzden varsayilan batch 18;
kalan semboller `--wait` saniye sonra ikinci turda cekilir.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE = ROOT / "config" / "universe.txt"
DEFAULT_DB = Path.home() / ".local" / "share" / "opencode" / "opencode.db"
DEFAULT_URL = "https://crypto-multiagent-production.up.railway.app/upload-payload"
DEFAULT_UPLOAD_TOKEN = "mG4Y9N1LPe6Sgc2MuZb0HVIDn5JTAkvqoUayrx7Wl8FQ3iws"
MCP_URL = "https://www.alertachart.com/mcp"
TOKEN_URL = "https://www.alertachart.com/oauth/token"


# ------------------------------------------------------------------ kimlik
def _now_ms() -> int:
    return int(time.time() * 1000)


def load_oauth(db: Path, label: str = "alertachart") -> tuple[dict, callable]:
    """opencode DB'sinden kimligi oku; geri yazma fonksiyonunu da dondur."""
    con = sqlite3.connect(str(db))
    row = con.execute(
        "select id, value from credential where integration_id like 'mcp_%' and label=?",
        (label,),
    ).fetchone()
    if not row:
        raise SystemExit(f"kimlik yok: {db} (label={label})")
    cid, raw = row
    data = json.loads(raw)

    def save(d: dict) -> None:
        con.execute("update credential set value=?, time_updated=? where id=?",
                    (json.dumps(d), _now_ms(), cid))
        con.commit()

    return data, save


def load_file(path: Path) -> tuple[dict, callable]:
    data = json.loads(path.read_text("utf-8"))

    def save(d: dict) -> None:
        path.write_text(json.dumps(d, indent=1), encoding="utf-8")

    return data, save


def refresh_token(data: dict, save: callable, margin_s: int = 120) -> str:
    """Gecerli access token dondur; gerekirse refresh edip geri yaz."""
    if _now_ms() < int(data.get("expires") or 0) - margin_s * 1000:
        return data["access"]
    client_id = ((data.get("metadata") or {}).get("client") or {}).get("client_id")
    if not client_id:
        raise SystemExit("client_id yok; token yenilenemez")
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": data["refresh"],
        "client_id": client_id,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json", "User-Agent": "crypto-multiagent/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            tok = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"token yenileme hatasi HTTP {e.code}: {e.read().decode()[:200]}")
    data["access"] = tok["access_token"]
    if tok.get("refresh_token"):
        data["refresh"] = tok["refresh_token"]
    data["expires"] = _now_ms() + int(tok.get("expires_in") or 3600) * 1000
    meta = data.setdefault("metadata", {})
    meta["tokenType"] = tok.get("token_type") or "Bearer"
    if tok.get("scope"):
        meta["scope"] = tok["scope"]
    save(data)
    return data["access"]


# --------------------------------------------------------------------- mcp
class MCP:
    def __init__(self, access: str, url: str = MCP_URL):
        self.url = url
        self.h = {
            "Authorization": f"Bearer {access}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": "crypto-multiagent/1.0",
        }
        self.sid = None
        self.n = 0
        self._post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {},
            "clientInfo": {"name": "crypto-multiagent", "version": "1.0"}}})
        self.n = 1
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _post(self, body: dict) -> dict | None:
        req = urllib.request.Request(self.url, data=json.dumps(body).encode(),
                                     method="POST", headers=self.h)
        with urllib.request.urlopen(req, timeout=90) as r:
            raw = r.read().decode("utf-8", "replace")
            sid = r.headers.get("mcp-session-id")
        if sid:
            self.sid = sid
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


# ------------------------------------------------------------------ payload
def build_symbol(sym: str, of: dict, lab: dict) -> dict | None:
    rows = of.get("rows") or []
    if not rows:
        return None
    last = rows[-1]
    w = [{
        "b": x.get("bars"), "px": x.get("price_change_pct"),
        "cvdp": (x.get("cvd_perp_usd") or 0) / 1e6,
        "cvds": (x.get("cvd_spot_usd") or 0) / 1e6,
        "oi": x.get("open_interest_change_pct"),
        "nl": x.get("net_longs_opened"), "ns": x.get("net_shorts_opened"),
        "ll": x.get("liquidated_longs_usd"), "ls": x.get("liquidated_shorts_usd"),
    } for x in (of.get("windows") or [])]
    venues = [{"v": v.get("venue"), "cvd": (v.get("cvd_usd") or 0) / 1e3}
              for v in (of.get("cvd_by_venue") or [])
              if "perpetual" in (v.get("venue") or "").lower()]
    fund = {f.get("venue"): f.get("funding_8h_pct")
            for f in (of.get("funding_by_venue") or [])}
    le = of.get("liquidation_events") or {}
    out = {
        "bar": last.get("time"), "price": last.get("close"), "w": w,
        "venues": venues, "fund": fund,
        "oi_usd": (of.get("last_open_interest") or {}).get("usd"),
        "lab": [{"m": m.get("module"), "v": m.get("value"), "r": m.get("reading"),
                 "ok": m.get("available")} for m in (lab.get("modules") or [])],
        "errors": [],
    }
    if le.get("since"):
        out["liq"] = {
            "since": le["since"],
            "l": {"count": (le.get("longs") or {}).get("count"),
                  "usd": (le.get("longs") or {}).get("usd")},
            "s": {"count": (le.get("shorts") or {}).get("count"),
                  "usd": (le.get("shorts") or {}).get("usd")},
            "top": [{"side": x.get("side"), "usd": x.get("usd"),
                     "price": x.get("price"), "venue": x.get("venue")}
                    for x in (le.get("largest") or [])[:3]],
        }
    return out


def load_universe() -> list[str]:
    if not UNIVERSE.is_file():
        raise SystemExit(f"evren yok: {UNIVERSE}")
    return [ln.strip() for ln in UNIVERSE.read_text("utf-8").splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def fetch(mcp: MCP, syms: list[str], tf: str, bars: int) -> tuple[dict, list]:
    out, report = {}, []
    for sym in syms:
        try:
            of = mcp.call("get_orderflow", {"symbol": sym, "timeframe": tf,
                                            "bars": bars, "by_venue": True})
            lab = mcp.call("get_chain_lab", {"symbol": sym, "timeframe": tf,
                                             "language": "tr"})
        except Exception as exc:
            report.append({"sym": sym, "error": str(exc)[:160]})
            continue
        b = build_symbol(sym, of, lab)
        if not b:
            report.append({"sym": sym, "error": "bos satir"})
            continue
        out[sym] = b
        report.append({"sym": sym, "bar": b["bar"], "px": b["price"],
                       "w": len(b["w"]), "v": len(b["venues"]), "lab": len(b["lab"])})
    return out, report


def upload(payload: dict, url: str, token: str) -> str:
    req = urllib.request.Request(
        url, data=json.dumps(payload, ensure_ascii=False).encode(), method="POST",
        headers={"Content-Type": "application/json", "X-Upload-Token": token},
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return f"HTTP {r.status} {r.read().decode()[:200]}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", default="", help="virgulle ayrilmis; bos = config/universe.txt")
    ap.add_argument("--tf", default="15m")
    ap.add_argument("--bars", type=int, default=24)
    ap.add_argument("--batch", type=int, default=18, help="10 dk basina orderflow siniri ~20")
    ap.add_argument("--wait", type=int, default=600, help="batchler arasi bekleme (sn)")
    ap.add_argument("--upload-url", default=os.environ.get("UPLOAD_URL") or DEFAULT_URL)
    ap.add_argument("--upload-token", default=os.environ.get("PAYLOAD_UPLOAD_TOKEN")
                    or DEFAULT_UPLOAD_TOKEN)
    ap.add_argument("--local", action="store_true", help="Render'a yukleme; cache'e yaz")
    ap.add_argument("--oauth-file", default="")
    ap.add_argument("--opencode-db", default=str(DEFAULT_DB))
    ap.add_argument("--label", default="alertachart")
    a = ap.parse_args(argv)

    env_token = os.environ.get("ALERTACHART_ACCESS_TOKEN", "").strip()
    if env_token:
        access = env_token
        save = None
    elif a.oauth_file:
        data, save = load_file(Path(a.oauth_file))
        access = refresh_token(data, save)
    else:
        data, save = load_oauth(Path(a.opencode_db), a.label)
        access = refresh_token(data, save)

    syms = ([s.strip() for s in a.symbols.split(",") if s.strip()]
            if a.symbols else load_universe())
    mcp = MCP(access)

    symbols: dict = {}
    reports: list = []
    batches = [syms[i:i + max(1, a.batch)] for i in range(0, len(syms), max(1, a.batch))]
    for i, part in enumerate(batches):
        got, rep = fetch(mcp, part, a.tf, a.bars)
        symbols.update(got)
        reports.extend(rep)
        print(f"[tur {i + 1}/{len(batches)}] {len(got)}/{len(part)} sembol", flush=True)
        if i < len(batches) - 1 and a.wait > 0:
            print(f"  rate limit: {a.wait}s bekleniyor...", flush=True)
            time.sleep(a.wait)

    try:
        macro = mcp.call("get_macro", {})
        macro_map = {s["symbol"]: {"latest": s.get("latest"), "change": s.get("change"),
                                   "change_1y": s.get("change_1y")}
                     for s in (macro.get("series") or []) if s.get("symbol")}
    except Exception as exc:
        print(f"macro atlandi: {str(exc)[:120]}", flush=True)
        macro_map = {}

    payload = {"macro": macro_map, "symbols": symbols}

    for r in reports:
        if r.get("error"):
            print(f"  HATA {r['sym']:16s} {r['error']}", flush=True)
        else:
            print(f"  {r['sym']:16s} {r['bar']}  px {r['px']}  w{r['w']} v{r['v']} lab{r['lab']}",
                  flush=True)
    print(f"\n{len(symbols)} sembol · makro {len(macro_map)} · {a.tf}", flush=True)

    if a.local:
        cache = ROOT / "cache" / "alertachart"
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "_payload.json").write_text(json.dumps(payload, ensure_ascii=False),
                                             encoding="utf-8")
        import subprocess
        return subprocess.run([sys.executable, str(ROOT / "tools" / "apply_payload.py"),
                               "--tf", a.tf], cwd=str(ROOT)).returncode

    if not symbols:
        print("anlamli veri yok; yuklenmedi (mevcut overlay korunur)", flush=True)
        return 1
    if not a.upload_token:
        raise SystemExit("PAYLOAD_UPLOAD_TOKEN yok (--upload-token veya ortam)")
    print(upload(payload, a.upload_url, a.upload_token), flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    raise SystemExit(main())
