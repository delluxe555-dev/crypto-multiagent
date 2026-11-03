#!/usr/bin/env python3
"""risk_debate.py — TradingAgents'taki 'agresif / muhafazakâr / nötr risk görüşü' fikrinin bizim sisteme küçük prototipi.
DANGER ZONE YOK: risk_rules.py'ye dokunmaz, canlı trader'a BAĞLI DEĞİL. Yalnızca öneri üretir; kural tabanlı risk (risk_rules.size) sonucu üst sınırdır.
Güvenlik tasarımı: LLM çıktısı pozisyonu yalnızca KÜÇÜLTEBİLİR/VETO edebilir; büyütemez, stop'u genişletemez.

Modlar (LLM çağrı sayısı):
  single   : 1 çağrı  — tek istemde üç kişilik (agresif/muhafazakâr/nötr) JSON + deterministik birleştirme        [önerilen]
  three    : 3 çağrı  — üç ayrı görüş çağrısı (paralel olmayan) + deterministik birleştirme
  manager  : 4 çağrı  — three + 'risk yöneticisi' sentez çağrısı (TradingAgents'ın orijinal akışına en yakın)
Kullanım:
  python3 risk_debate.py outputs/BTCUSDT_1h_2026-10-24T2100.json --mode single [--dry] [--out dosya.json]
  --dry: LLM çağırmaz (sahte yanıt) — yalnızca boru hattı testi, SONUÇ DEĞİLDİR.
"""
import os, sys, json, time, argparse, statistics, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

RULE = "Yalnızca verilen veriyi kullan, veri uydurma. Türkçe, kısa ve net yaz. Sayıları ham veriden birebir aktar."
PERSONA = {
    "AGRESIF": "Sen AGRESİF risk görüşünü savunan analistsin: fırsatı kaçırma maliyetini vurgula, yüksek getirili girişi destekle; yine de veri dışı sayı kullanma.",
    "MUHAFAZAKAR": "Sen MUHAFAZAKÂR risk görüşünü savunan analistsin: sermaye korumayı, kayma/komisyon maliyetini, tersine dönüş ve likidasyon riskini vurgula; en kötü senaryoyu veriyle göster.",
    "NOTR": "Sen NÖTR (dengeli) risk görüşünü savunan analistsin: iki uç görüşün zayıf noktalarını eleştir, ölçülü ve veriye en sadık yolu seç.",
}
VIEW_SCHEMA = ('SADECE JSON (anahtarlar aynen): {"onay":true|false,"size_mult":0-1 arası sayı (kural-tabanlı pozisyonun kaçta kaçı),'
               '"stop_atr_mult":<sayı veya null>,"gerekce":"<en fazla 45 kelime>"}')

def _ctx_text(o):
    """Risk görüşlerine verilen bağlam: ham veri + komite kararı + kural-tabanlı risk."""
    verdict = o.get("hakem") or o.get("karar") or {}
    return (f"Ham veri:\n{o.get('tech_data','(yok)')}\n\nTürev/duygu verisi:\n{str(o.get('sentiment_data',''))[:1800]}\n\n"
            f"Komite kararı:\n{json.dumps(verdict, ensure_ascii=False)}\n\nKural tabanlı risk (üst sınır, değiştirilemez):\n{json.dumps(o.get('risk_kural'), ensure_ascii=False)}")

def _mock(system, user):
    if "üç kişilik" in system: return json.dumps({k: {"onay": True, "size_mult": v, "stop_atr_mult": None, "gerekce": "DRY-RUN"} for k, v in (("AGRESIF", 1.0), ("MUHAFAZAKAR", 0.5), ("NOTR", 0.75))})
    if "risk yöneticisi" in system: return json.dumps({"onay": True, "size_mult": 0.75, "gerekce": "DRY-RUN"})
    return json.dumps({"onay": True, "size_mult": 0.75, "stop_atr_mult": None, "gerekce": "DRY-RUN"})

def parse_json(txt):
    m = re.search(r"\{.*\}", txt, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None

class Meter:
    def __init__(self): self.calls = []
    def chat(self, llm, system, user, role="deep", max_tokens=1200, dry=False):
        t0 = time.time(); txt = _mock(system, user) if dry else llm.chat(system, user, max_tokens=max_tokens, role=role)
        self.calls.append({"s": round(time.time() - t0, 2), "chars_in": len(system) + len(user), "chars_out": len(txt), "provider": (llm.last_provider() if (llm and not dry) else "dry")})
        return txt
    def summary(self):
        n = len(self.calls); ci = sum(c["chars_in"] for c in self.calls); co = sum(c["chars_out"] for c in self.calls)
        return {"llm_calls": n, "wall_s": round(sum(c["s"] for c in self.calls), 1), "chars_in": ci, "chars_out": co,
                "approx_tokens_in": int(ci / 3.2), "approx_tokens_out": int(co / 3.2), "providers": sorted(set(c["provider"] for c in self.calls))}

def _num(x, lo=0.0, hi=1.0):
    try: return min(hi, max(lo, float(x)))
    except (TypeError, ValueError): return None

def merge(views, rule_pos, rule_blocked):
    """Deterministik birleştirme: çoğunluk onayı, medyan size_mult (<=1), kural-tabanlı pozisyon ÜST SINIR. Parse edilemeyen görüş muhafazakâr sayılır (0)."""
    ok = [v for v in views.values() if isinstance(v, dict)]
    mults = [(_num(v.get("size_mult")) if _num(v.get("size_mult")) is not None else 0.0) for v in ok]
    approvals = [bool(v.get("onay")) for v in ok]
    approve = sum(approvals) > len(approvals) / 2 if approvals else False
    sm = statistics.median(mults) if mults else 0.0
    sm = 0.0 if not approve else min(1.0, sm)
    pos = 0.0 if rule_blocked else round(rule_pos * sm, 2)
    return {"onay": approve, "size_mult": round(sm, 3), "pozisyon_usd_kural": rule_pos, "pozisyon_usd_onerilen": pos,
            "not": "Yalnızca küçültme/veto; stop kural-tabanlı kalır; canlı sisteme bağlı değil.", "n_views_parsed": len(ok)}

def run(o, mode="single", dry=False):
    llm = None
    if not dry:
        import llm
        # canlı sistemi korumak için: kota-ölü işaretini DİSKE yazma (llm_dead.json'u yalnız canlı trader günceller)
        llm._mark_dead = lambda key, e: llm._dead.add(key)
    M = Meter(); ctx = _ctx_text(o); rk = o.get("risk_kural") or {}
    rule_pos = float(rk.get("pozisyon_usd") or 0); blocked = rk.get("engel")
    views = {}; mgr = None
    if mode == "single":
        sysm = f"Sen üç kişilik bir risk komitesisin (AGRESİF, MUHAFAZAKÂR, NÖTR). {RULE}"
        usr = (f"{ctx}\n\nHer üç kişilik için ayrı görüş ver. {VIEW_SCHEMA.replace('SADECE JSON (anahtarlar aynen): ', '')} "
               'SADECE JSON: {"AGRESIF":{...},"MUHAFAZAKAR":{...},"NOTR":{...}} (her biri yukarıdaki anahtarlarla).')
        txt = M.chat(llm, sysm, usr, dry=dry); j = parse_json(txt) or {}
        views = {k: j.get(k) for k in PERSONA}
    else:
        for k, p in PERSONA.items():
            txt = M.chat(llm, f"{p} {RULE}", f"{ctx}\n\n{VIEW_SCHEMA}", dry=dry); views[k] = parse_json(txt)
        if mode == "manager":
            sysm = f"Sen risk yöneticisisin (portföy yöneticisi). {RULE}"
            txt = M.chat(llm, sysm, f"{ctx}\n\nÜç görüş:\n{json.dumps(views, ensure_ascii=False)}\n\nSentez: " + VIEW_SCHEMA, dry=dry); mgr = parse_json(txt)
    merged = merge(views, rule_pos, blocked)
    if mgr:   # yönetici çıktısı yalnızca daha da küçültebilir
        mm = _num(mgr.get("size_mult"));
        if mm is not None: merged["manager_size_mult"] = mm; merged["size_mult"] = round(min(merged["size_mult"], mm), 3) if mgr.get("onay") else 0.0; merged["pozisyon_usd_onerilen"] = 0.0 if blocked else round(rule_pos * merged["size_mult"], 2)
    res = {"mode": mode, "dry": dry, "views": views, "manager": mgr, "merged": merged, "cost": M.summary()}
    try:   # sayı doğrulama (grounding.py): görüş gerekçelerindeki uydurma sayıları işaretle
        import grounding
        txt = " ".join(str(v.get("gerekce", "")) for v in list(views.values()) + [mgr or {}] if isinstance(v, dict))
        ctxo = {k: o.get(k) for k in grounding.CONTEXT_FIELDS if o.get(k) is not None}; ctxo["risk_kural"] = o.get("risk_kural"); ctxo["hakem"] = o.get("hakem")
        r = grounding.validate(txt, ctxo, grounding._prompt_text()); res["grounding"] = grounding.summarize(r)
        res["grounding"]["doğrulanamadı_liste"] = [x["raw"] for x in r if x["durum"] == "doğrulanamadı"]
    except Exception as e: res["grounding"] = f"hata: {e}"
    return res

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("file"); ap.add_argument("--mode", choices=["single", "three", "manager"], default="single")
    ap.add_argument("--dry", action="store_true"); ap.add_argument("--out")
    a = ap.parse_args(); o = json.load(open(a.file)); res = run(o, a.mode, a.dry)
    print(json.dumps(res, ensure_ascii=False, indent=1))
    if a.out: json.dump(res, open(a.out, "w"), ensure_ascii=False, indent=1)
