"""Karar arsivi: komite kararlarini, katman goruntulerini ve durum ozetini saklar.

Neden
-----
`runs/live/<stamp>/decision_*.json` her 5 dakikada 23 dosya uretiyor
(gunde ~6.600 dosya, ~25 MB). Hicbiri silinmezse disk siser; hepsi silinirse
"SL olan pozisyonda komite ne oyladi, hangi kapi kesti" sorusu bir daha
cevaplanamaz. Bu arac ikisini birlikte yapar: once kalici arsive yazar,
sonra ham dosyalari temizler.

Arsiv yapisi (`runs/archive/` altinda)
--------------------------------------
    decisions/YYYY-MM-DD.jsonl   her sembol+bar icin TEK kompakt karar satiri
                                 (oylar, vetolar, seviyeler, aralik konumu)
    entries/YYYY-MM-DD.jsonl     pozisyon ACAN kararin tam dokumu
    layers/YYYY-MM-DD/HH.json    _market / _extras / _macro saatlik goruntusu
    state/YYYY-MM-DD.json        paper + triggers gunluk ozeti

Kullanim
--------
    python3 tools/archive.py                 # bir tur (varsayilan)
    python3 tools/archive.py --dry-run       # yazmadan/silmeden ne yapardi
    python3 tools/archive.py --no-clean      # arsivle, ham dosyalari silme
    python3 tools/archive.py --report        # sadece arsiv ozeti

Env
---
    ARCHIVE_RAW_HOURS=36     ham karar klasorleri bu yastan sonra silinir
    ARCHIVE_KEEP_DAYS=180    arsiv gun dosyalari bu yastan sonra silinir
    ARCHIVE_MAX_MB=800       arsiv bu boyutu asarsa en eski gunler silinir
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

LIVE = Path(os.environ.get("LIVE_DIR") or ROOT / "runs" / "live")
ARCH = Path(os.environ.get("ARCHIVE_DIR") or ROOT / "runs" / "archive")
CACHE = Path(os.environ.get("CA_AC_CACHE") or ROOT / "cache" / "alertachart")

RAW_HOURS = float(os.environ.get("ARCHIVE_RAW_HOURS") or 36)
KEEP_DAYS = int(os.environ.get("ARCHIVE_KEEP_DAYS") or 180)
MAX_MB = float(os.environ.get("ARCHIVE_MAX_MB") or 800)
# Bir klasor bu yastan gencse arsivlenmez (yazma yarim kalmis olabilir).
MIN_AGE_H = float(os.environ.get("ARCHIVE_MIN_AGE_H") or 2.0)
# Karar satirini tutmak icin esik: yon payi bunun altindaysa ve veto yoksa
# (yani "aday bile olmadi") satir arsive yazilmaz; gurultu birikmesin.
MIN_SHARE = float(os.environ.get("ARCHIVE_MIN_SHARE") or 0.5)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(p: Path):
    try:
        return json.loads(p.read_text("utf-8"))
    except Exception:
        return None


def _day(iso: str | None) -> str:
    """ISO zaman -> UTC gun (YYYY-MM-DD). Cozulemezse bugun."""
    if not iso:
        return _now().strftime("%Y-%m-%d")
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return t.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return _now().strftime("%Y-%m-%d")


def _append_jsonl(p: Path, rows: list[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def _load_jsonl(p: Path) -> dict:
    """Dosyayi oku, (symbol, bar) anahtarli sozluge cevir (son satir kazanir)."""
    out: dict = {}
    if not p.is_file():
        return out
    try:
        for line in p.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            # Giris kayitlari pozisyon kimligiyle, kararlar (sembol, bar) ile anahtarlanir.
            k = r.get("_position_id") or (r.get("symbol"), r.get("bar"))
            if k and (k[0] if isinstance(k, tuple) else k):
                out[k] = r
    except Exception:
        pass
    return out


def _write_jsonl(p: Path, rows: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in sorted(rows.values(), key=lambda x: (str(x.get("bar")), str(x.get("symbol")))):
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    tmp.replace(p)


# ------------------------------------------------------------------ kompakt karar
def compact(dec: dict) -> dict:
    """Karar dosyasindan analiz icin gereken alanlar (dosya boyutunun ~1/5'i)."""
    c = dec.get("consensus") or {}
    votes = {}
    for name, v in (dec.get("votes") or {}).items():
        if not isinstance(v, dict):
            continue
        votes[name] = {"side": v.get("side"), "conf": v.get("conf"),
                       "advisory": bool(v.get("advisory"))}
    vetoes = []
    for v in dec.get("vetoes") or []:
        if isinstance(v, dict):
            vetoes.append({"by": v.get("by"), "why": v.get("why")})
    mkt = dec.get("market") or {}
    ex = dec.get("extras") or {}
    return {
        "symbol": dec.get("symbol"), "tf": dec.get("tf"), "bar": dec.get("bar"),
        "built_at": dec.get("built_at"), "price": dec.get("price"),
        "action": dec.get("action"), "mode": dec.get("mode"),
        "trigger": dec.get("trigger"),
        "consensus": {"buy": c.get("buy"), "sell": c.get("sell"), "hold": c.get("hold"),
                      "share": c.get("share"), "candidate": c.get("candidate"),
                      "valid": c.get("valid_votes"), "dir": c.get("directional")},
        "votes": votes, "vetoes": vetoes, "notes": dec.get("notes") or [],
        "levels": dec.get("levels") or {},
        "range": dec.get("range"), "slope": dec.get("slope"),
        "extension_atr": dec.get("extension_atr"),
        "rr_floor": dec.get("rr_floor"), "rr_market_floor": dec.get("rr_market_floor"),
        "market": {"breadth": mkt.get("breadth_pct"), "squeeze": mkt.get("squeeze")},
        "extras": {"age_min": ex.get("age_min"), "news": ex.get("news"),
                   "scan_adv": ex.get("scan_adv"), "scan_dec": ex.get("scan_dec"),
                   "options": ex.get("options")},
        "overlay": dec.get("overlay") or {},
    }


def _worth_keeping(dec: dict) -> bool:
    if (dec.get("action") or "HOLD").upper() != "HOLD":
        return True
    if (dec.get("mode") or "none") != "none":
        return True
    if dec.get("vetoes"):
        return True
    share = float(((dec.get("consensus") or {}).get("share")) or 0)
    return share >= MIN_SHARE


# ------------------------------------------------------------------ arsiv turlari
def entry_meta() -> dict:
    """Pozisyonu acan karar dosyalari: yol -> pozisyon bilgisi.

    Ayni bar icin birden fazla karar dosyasi olabilir (5 dakikalik dongu ayni
    bari tekrar karara bagliyor). Pozisyonu acan karar, `triggers.json`daki
    `decision` yoludur; "o barin en yeni karari" degil.
    """
    st = _read_json(LIVE / "triggers.json") or {}
    out: dict = {}
    for pid, pos in (st.get("positions") or {}).items():
        if not isinstance(pos, dict):
            continue
        p = pos.get("decision")
        if not p:
            continue
        out[Path(str(p))] = {"pid": pid, "symbol": pos.get("symbol"),
                             "bar": pos.get("opened_bar"),
                             "ref_entry": pos.get("ref_entry")}
    return out


def _entry_row(dec: dict, meta: dict | None, exact: bool) -> dict:
    """Giris satiri: karar dokumu + hangi pozisyona ait oldugu."""
    row = dict(dec)
    row["_decision_exact"] = bool(exact)
    if meta:
        row["_position_id"] = meta.get("pid")
        row["_position_bar"] = meta.get("bar")
        row["_position_ref_entry"] = meta.get("ref_entry")
        ref = meta.get("ref_entry")
        try:
            same = abs(float((dec.get("levels") or {}).get("entry")) - float(ref)) < 1e-9
        except (TypeError, ValueError):
            same = True
        if ref is not None and not same:
            # Dosya sonradan degismis: bu karar pozisyonu acan karar degil.
            row["_ref_mismatch"] = True
    return row


def archive_decisions(dry: bool = False, clean: bool = True) -> dict:
    """Ham karar klasorlerini arsive tasi; eskilerini sil.

    Her turda tum klasorleri yeniden okumamak icin `.marker` dosyasi son
    arsivlenen klasorun adini tutar; yalniz ondan yeni klasorler islenir.
    Klasor adlari `YYYYMMDDTHHMMZ` oldugu icin alfabetik sira = kronolojik sira.
    """
    if not LIVE.is_dir():
        return {"ok": False, "error": f"yok: {LIVE}"}
    now = _now()
    cutoff = now - timedelta(hours=RAW_HOURS)
    young = now - timedelta(hours=MIN_AGE_H)
    marker_p = ARCH / ".marker"
    marker = ""
    if marker_p.is_file():
        try:
            marker = marker_p.read_text("utf-8").strip()
        except OSError:
            marker = ""
    by_path = entry_meta()
    ekeys = {(m.get("symbol"), m.get("bar")) for m in by_path.values()
             if m.get("symbol") and m.get("bar")}
    # Yol kaybolmus olsa da pozisyonun referansi bilinir: eslesmeyi isaretlemek icin.
    ref_by_key = {(m.get("symbol"), m.get("bar")): m for m in by_path.values()}
    # Pozisyonu acan dosya hala duruyorsa (36 saat) dogrudan ondan oku:
    # marker/klasor taramasindan bagimsiz, boylece yanlis arsivlenmis kayit duzelir.
    ent_cand: dict[str, dict] = {}
    for p, meta in by_path.items():
        if not p.is_file():
            continue
        dec = _read_json(p)
        if not isinstance(dec, dict) or not dec.get("symbol"):
            continue
        day = _day(dec.get("bar") or dec.get("built_at"))
        key = (dec.get("symbol"), dec.get("bar"))
        ent_cand.setdefault(day, {})[key] = (
            True, dec.get("built_at") or "", _entry_row(dec, meta, True))
    dirs = []
    for d in sorted(LIVE.iterdir()):
        if not d.is_dir() or not d.name[:8].isdigit():
            continue
        if marker and d.name <= marker:
            continue
        try:
            mt = datetime.fromtimestamp(d.stat().st_mtime, timezone.utc)
        except OSError:
            continue
        if mt > young:
            continue  # henuz yaziliyor olabilir; sonraki turda
        dirs.append((d, mt))

    # Arsivlenecek gunler: once var olan gun dosyalarini yukle, uzerine ekle.
    days: dict[str, dict] = {}
    entries: dict[str, dict] = {}
    scanned = kept = 0
    processed = []
    for d, mt in dirs:
        files = sorted(d.glob("decision_*.json"))
        if not files:
            processed.append((d, mt))
            continue
        rows_by_day: dict[str, dict] = {}
        for f in files:
            dec = _read_json(f)
            if not isinstance(dec, dict) or not dec.get("symbol"):
                continue
            scanned += 1
            key = (dec.get("symbol"), dec.get("bar"))
            day = _day(dec.get("bar") or dec.get("built_at"))
            if key in ekeys:
                # Tam dokum YALNIZ pozisyonu acan dosyadan alinir; ayni barin
                # sonraki karari baska bir karar olabilir (farkli mod/oylama).
                meta = by_path.get(f)
                is_exact = meta is not None
                if meta is None:
                    meta = ref_by_key.get(key)  # yolu kayip: yalniz isaretleme icin
                built = dec.get("built_at") or ""
                slot = ent_cand.setdefault(day, {})
                prev = slot.get(key)
                if (prev is None
                        or (is_exact and not prev[0])
                        or (is_exact == prev[0] and built >= prev[1])):
                    slot[key] = (is_exact, built, _entry_row(dec, meta, is_exact))
            if _worth_keeping(dec):
                rows_by_day.setdefault(day, {})[key] = compact(dec)
                kept += 1
        for day, rows in rows_by_day.items():
            if day not in days:
                days[day] = _load_jsonl(ARCH / "decisions" / f"{day}.jsonl")
            days[day].update(rows)
        processed.append((d, mt))

    for day, slot in ent_cand.items():
        if day not in entries:
            entries[day] = _load_jsonl(ARCH / "entries" / f"{day}.jsonl")
        for key, (is_exact, _built, row) in slot.items():
            ek = row.get("_position_id") or key
            cur = entries[day].get(ek)
            if is_exact:
                entries[day][ek] = row
            elif cur is None:
                # Yol bilinmiyor/dosya silinmis: geri dusum isaretli yaz.
                entries[day][ek] = {**row, "_decision_exact": False}
                if row.get("_position_id"):
                    # Eski (kimliksiz) ayni-sembol/bar satirini birakma.
                    for k in list(entries[day]):
                        r = entries[day][k]
                        if (k != ek and not r.get("_position_id")
                                and (r.get("symbol"), r.get("bar"))
                                == (row.get("symbol"), row.get("bar"))):
                            del entries[day][k]
        # Ayni sembol+bar icin tam dokum varsa geri dusum satirini at.
        exact_keys = {(r.get("symbol"), r.get("bar"))
                      for r in entries[day].values() if r.get("_decision_exact")}
        entries[day] = {k: r for k, r in entries[day].items()
                        if r.get("_decision_exact")
                        or (r.get("symbol"), r.get("bar")) not in exact_keys}

    # Eski (kimliksiz) giris satirlarini da pozisyona bagla: ham dosya silinmis
    # olsa bile "bu satir hangi pozisyon, referansi tutuyor mu" bilinir.
    for p in sorted((ARCH / "entries").glob("*.jsonl")):
        day = p.stem
        rows = entries.get(day)
        if rows is None:
            rows = _load_jsonl(p)
        changed = False
        for k, r in list(rows.items()):
            if r.get("_position_id"):
                continue
            m = ref_by_key.get((r.get("symbol"), r.get("bar")))
            if not m:
                continue
            rows.pop(k)
            rows[m["pid"]] = _entry_row(r, m, False)
            changed = True
        if changed:
            entries[day] = rows

    if dry:
        return {"ok": True, "dry_run": True, "dirs": len(processed),
                "scanned": scanned, "kept_rows": kept,
                "days": {k: len(v) for k, v in days.items()}}

    for day, rows in days.items():
        _write_jsonl(ARCH / "decisions" / f"{day}.jsonl", rows)
    for day, rows in entries.items():
        _write_jsonl(ARCH / "entries" / f"{day}.jsonl", rows)

    removed = 0
    if clean:
        # Silme, marker'dan bagimsiz: yasi RAW_HOURS'u gecen tum ham klasorler
        # gider (daha once arsivlenmis olsalar bile).
        for d in sorted(LIVE.iterdir()):
            if not d.is_dir() or not d.name[:8].isdigit():
                continue
            try:
                mt = datetime.fromtimestamp(d.stat().st_mtime, timezone.utc)
            except OSError:
                continue
            if mt >= cutoff:
                continue
            try:
                shutil.rmtree(d)
                removed += 1
            except OSError as exc:
                print(f"silinemedi {d.name}: {exc}", flush=True)
    if processed:
        try:
            marker_p.parent.mkdir(parents=True, exist_ok=True)
            marker_p.write_text(processed[-1][0].name, "utf-8")
        except OSError:
            pass

    return {"ok": True, "dirs_archived": len(processed), "dirs_removed": removed,
            "scanned": scanned, "kept_rows": kept,
            "days": {k: len(v) for k, v in days.items()}}


def snapshot_layers(dry: bool = False) -> dict:
    """Saatlik katman goruntusu: `_market`, `_extras`, `_macro`."""
    hour = _now().strftime("%Y-%m-%d")
    hh = _now().strftime("%H")
    out = ARCH / "layers" / hour / f"{hh}.json"
    if out.is_file():
        return {"ok": True, "skipped": True, "path": str(out)}
    snap = {"asof": _now().isoformat(timespec="seconds")}
    for name in ("_market", "_extras", "_macro"):
        d = _read_json(CACHE / f"{name}.json")
        if d is not None:
            snap[name.lstrip("_")] = d
    if len(snap) == 1:
        return {"ok": True, "skipped": True, "reason": "katman dosyasi yok"}
    if dry:
        return {"ok": True, "dry_run": True, "path": str(out), "keys": list(snap)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False), "utf-8")
    return {"ok": True, "path": str(out), "bytes": out.stat().st_size}


def snapshot_state(dry: bool = False) -> dict:
    """Gunluk durum ozeti: paper hesabi + triger durumlari."""
    day = _now().strftime("%Y-%m-%d")
    out = ARCH / "state" / f"{day}.json"
    if out.is_file():
        return {"ok": True, "skipped": True, "path": str(out)}
    snap = {"asof": _now().isoformat(timespec="seconds")}
    try:
        import paper  # noqa: WPS433
        paper.configure(LIVE)
        s = paper.summary(limit=0)
        snap["paper"] = {"balance": s.get("balance"), "pnl": s.get("pnl"),
                         "pnl_pct": s.get("pnl_pct"), "trades": len(s.get("history") or []),
                         "open": s.get("open") or [], "history": s.get("history") or []}
    except Exception as exc:  # noqa: BLE001
        snap["paper_error"] = f"{type(exc).__name__}: {exc}"
    st = _read_json(LIVE / "triggers.json") or {}
    rows = []
    for pid, pos in (st.get("positions") or {}).items():
        if not isinstance(pos, dict):
            continue
        rows.append({k: pos.get(k) for k in (
            "symbol", "action", "status", "mode", "entry", "sl", "sl_orig", "tp1", "tp2",
            "tp1_done", "sl_moved", "opened_at", "opened_bar", "closed_at", "exit",
            "r", "decision")})
    snap["triggers"] = rows
    if dry:
        return {"ok": True, "dry_run": True, "path": str(out), "triggers": len(rows)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snap, ensure_ascii=False), "utf-8")
    return {"ok": True, "path": str(out), "bytes": out.stat().st_size,
            "triggers": len(rows)}


def cleanup_archive(dry: bool = False) -> dict:
    """Eski arsiv gunlerini ve boyut asimini temizle."""
    removed, freed = [], 0
    if not ARCH.is_dir():
        return {"ok": True, "removed": 0, "mb": 0}
    cutoff = (_now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    for sub in ("decisions", "entries"):
        d = ARCH / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.jsonl")):
            if f.stem < cutoff:
                if not dry:
                    try:
                        freed += f.stat().st_size
                        f.unlink()
                        removed.append(f"{sub}/{f.name}")
                    except OSError:
                        pass
    # boyut siniri: en eski gunlerden basla
    total = sum(f.stat().st_size for f in ARCH.rglob("*") if f.is_file())
    if total > MAX_MB * 1024 * 1024:
        files = sorted((f for f in ARCH.rglob("*") if f.is_file()),
                       key=lambda f: f.name)
        for f in files:
            if total <= MAX_MB * 1024 * 1024 * 0.9:
                break
            if f.suffix not in (".jsonl", ".json"):
                continue
            if not dry:
                try:
                    sz = f.stat().st_size
                    f.unlink()
                    total -= sz
                    freed += sz
                    removed.append(str(f.relative_to(ARCH)))
                except OSError:
                    pass
    return {"ok": True, "removed": len(removed), "files": removed[:20],
            "freed_mb": round(freed / 1024 / 1024, 2)}


def report() -> dict:
    """Arsiv ozeti: hangi gun hangi dosya, boyut (satir saymaz; hizli)."""
    out = {"dir": str(ARCH), "exists": ARCH.is_dir(), "files": [], "mb": 0}
    if not ARCH.is_dir():
        return out
    total = 0
    for sub in ("decisions", "entries", "state"):
        d = ARCH / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json*")):
            try:
                size = f.stat().st_size
            except OSError:
                continue
            total += size
            out["files"].append({"name": f"{sub}/{f.name}", "kb": round(size / 1024, 1)})
    lay = ARCH / "layers"
    if lay.is_dir():
        files = list(lay.rglob("*.json"))
        size = sum(f.stat().st_size for f in files)
        total += size
        out["files"].append({"name": "layers/", "files": len(files),
                             "kb": round(size / 1024, 1)})
    out["files"] = out["files"][-40:]
    out["mb"] = round(total / 1024 / 1024, 2)
    raw, raw_dirs = 0, 0
    if LIVE.is_dir():
        for d in LIVE.iterdir():
            if d.is_dir() and d.name[:8].isdigit():
                raw_dirs += 1
                raw += sum(f.stat().st_size for f in d.glob("decision_*.json"))
    out["raw_live_mb"] = round(raw / 1024 / 1024, 2)
    out["raw_live_dirs"] = raw_dirs
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-clean", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    if a.report:
        print(json.dumps(report(), ensure_ascii=False, indent=2))
        return 0
    r = archive_decisions(dry=a.dry_run, clean=not a.no_clean)
    l = snapshot_layers(dry=a.dry_run)
    s = snapshot_state(dry=a.dry_run)
    c = cleanup_archive(dry=a.dry_run)
    print(json.dumps({"decisions": r, "layers": l, "state": s, "cleanup": c},
                     ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
