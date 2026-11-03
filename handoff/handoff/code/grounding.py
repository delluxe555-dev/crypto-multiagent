#!/usr/bin/env python3
"""grounding.py — LLM metnindeki SAYISAL iddiaları, ajana verilen veri bağlamıyla karşılaştıran doğrulayıcı.
Bağımsız modül: trader.py / agents.py / llm.py'ye bağlı DEĞİL, hiçbir sayı üretmez/düzeltmez, yalnızca "doğrulanamadı" listeler.

Sınıflar (her sayısal iddia için):
  eşleşti        : bağlamdaki bir sayıyla (tolerans içinde; x1, x100, x0.01 birim dönüşümü dahil) birebir örtüşüyor
  türetilmiş     : bağlamdaki iki sayının farkı / oranı / % farkı olarak açıklanabiliyor (ör. "kritik seviyenin %2,9 üstünde", "~830$ uzaklık")
  prompt_sabiti  : ajana verilen komut metnindeki sabit (ör. %1 risk, 10.000$ portföy, ATR×1.5)
  doğrulanamadı  : yukarıdakilerden hiçbiri -> insan incelemesi gerekir (uydurma KANITI DEĞİL; ya uydurma ya da doğrulayıcının göremediği bir türetme)
Kullanım:
  python3 grounding.py --check outputs/BTCUSDT_1h_2026-10-24T2100.json [--rel-tol 0.005] [--no-derived] [-v]
  python3 grounding.py --scan "outputs/*_1h_*.json" "outputs/*_1d_*.json" --out outputs/grounding_report.json
  python3 grounding.py --text "Destek 4.35, RSI 62" --context-file veri.txt
"""
import re, sys, os, json, glob, argparse, itertools, math
HERE = os.path.dirname(os.path.abspath(__file__))
NUM = r"(?<![A-Za-z_\d.,])[-+−]?\d[\d.,]*(?:\s?(?:bin|milyon|milyar|mlr|mln)(?![A-Za-zÇĞİÖŞÜçğıöşü])|\s?[kKmMB](?![A-Za-zÇĞİÖŞÜçğıöşü]))?"
STAGE_FIELDS = ["teknik_analist", "duygu_analisti", "boga", "ayi", "hakem", "risk_llm", "risk"]
CONTEXT_FIELDS = ["tech_data", "sentiment_data", "extras", "memory", "lessons_block"]
SKIP_KEYS = {"guven", "pozisyon_usd", "onay"}          # ajanın kendi çıktısı (güven puanı, pozisyon büyüklüğü) -> veri iddiası değil

def _parse_variants(tok):
    """Sayı jetonunu olası değerlere çevir (TR/EN biçimleri). -> [(value, decimals)]  (decimals: iddianın son hane basamağı, ölçekle birlikte; k/M için negatif)"""
    t = tok.strip().replace("−", "-"); mult = 1.0; dshift = 0
    mm = re.search(r"\s?(bin|milyon|milyar|mlr|mln|k|K|M|B)$", t)
    if mm and len(t) > len(mm.group(0)):
        mult, dshift = {"bin": (1e3, 3), "k": (1e3, 3), "K": (1e3, 3), "milyon": (1e6, 6), "M": (1e6, 6), "milyar": (1e9, 9), "mlr": (1e9, 9), "mln": (1e6, 6), "B": (1e9, 9)}[mm.group(1)]
        t = t[:mm.start()].strip()
    neg = t.startswith("-"); t = t.lstrip("+-")
    t = t.rstrip(".,")
    if re.search(r"[.,]\d*0$", t) and not re.search(r"[.,]0{3}$", t): t = re.sub(r"(?<=[.,]\d)0+$|(?<=[.,]\d\d)0+$", "", t) if False else t
    if not t or not re.search(r"\d", t): return []
    out = []
    def add(s, dec):
        if "." in s and dec >= 5 and s.rstrip("0") != s: dec = len(s.split(".")[1].rstrip("0"))   # 0.00460000 -> 4 anlamlı hane
        try: v = float(s)
        except ValueError: return
        out.append(((-v if neg else v) * mult, dec - dshift))
    seps = re.findall(r"[.,]", t)
    if not seps: add(t, 0)
    else:
        last = max(t.rfind("."), t.rfind(",")); frac = t[last + 1:]; head = t[:last]; hs = re.sub(r"[.,]", "", head)
        if len(seps) == 1:
            if len(frac) == 3 and head and len(head) <= 3:      # 80.638 / 80,638 -> hem binlik hem ondalık olabilir
                add(hs + frac, 0); add(hs + "." + frac, 3)
            else: add(hs + "." + frac, len(frac))
        else:
            if len(set(seps)) == 1 and all(len(p) == 3 for p in re.split(r"[.,]", t)[1:]): add(re.sub(r"[.,]", "", t), 0)   # 1.234.567
            else: add(hs + "." + frac, len(frac))                                                                         # 1,234.56 / 1.234,56
    return out

def _is_trivial(tok, text, s, e):
    """Tarih/saat, madde numarası, indikatör periyodu, küçük sayma sayıları -> iddia sayılmaz."""
    pre = text[max(0, s - 14):s]; post = text[e:e + 3]; raw = tok.strip()
    if re.search(r"\d\s*[:/]\s*$", pre) or re.match(r"\s*[:/]\d", text[e:e + 3]): return True      # 21:00, 10-24
    if re.search(r"\d-$", pre) or re.match(r"-\d", post): return True
    if re.fullmatch(r"20\d\d", raw): return True
    if re.search(r"(^|\n)[ \t]*[-*•]?[ \t]*$", text[:s]) and (re.match(r"[.)]", post) or raw.endswith(".")) and re.fullmatch(r"\d{1,2}\.?", raw): return True   # "1." liste
    if re.search(r"(güven|guven|confidence)\W{0,3}$", pre.lower()): return True
    pct = "%" in text[max(0, s - 1):s] or "%" in post[:2]
    cur = "$" in post[:2] or "$" in text[max(0, s - 1):s]
    if re.fullmatch(r"\d{1,2}", raw) and not pct and not cur and not re.match(r"\s?(x|×)", post): return True   # "3 argüman", "2 kanıt", "10 mum"
    if re.search(r"(en fazla|max|ilk|son)\s*$", pre.lower()) and re.fullmatch(r"\d+", raw): return True
    return False

def extract_claims(text):
    """Metinden sayısal iddiaları çıkar. Her iddia: {raw, variants[(v,dec)], pct, ctx}"""
    claims = []; text = re.sub(r"\*\*|__|`", "", str(text))
    for m in re.finditer(NUM, text):
        tok = m.group(0); s, e = m.start(), m.end()
        if _is_trivial(tok, text, s, e): continue
        vs = _parse_variants(tok)
        if not vs: continue
        pct = "%" in text[max(0, s - 1):s] or text[e:e + 2].strip().startswith("%")
        mult = bool(re.match(r"\s?(x|×)", text[e:e + 3])) or bool(re.search(r"(x|×)\s?$", text[max(0, s - 3):s]))
        ctx = text[max(0, s - 30):e + 20].replace("\n", " ")
        claims.append({"raw": tok.strip(), "variants": vs, "pct": pct, "mult": mult, "ctx": ctx})
    return claims

def _flatten(o, acc):
    if isinstance(o, dict):
        for k, v in o.items(): _flatten(v, acc)
    elif isinstance(o, (list, tuple)):
        for v in o: _flatten(v, acc)
    elif isinstance(o, bool) or o is None: pass
    elif isinstance(o, (int, float)): acc.append(float(o))
    else: acc.extend(_numbers_from_text(str(o)))
    return acc

def _numbers_from_text(txt):
    out = []
    txt = re.sub(r"\*\*|__|`", "", txt)
    for m in re.finditer(NUM, txt):
        for v, d in _parse_variants(m.group(0)): out.append(v)
    return out

def build_context(ctx_obj, prompt_text=""):
    nums = _flatten(ctx_obj, [])
    consts = _numbers_from_text(prompt_text) if prompt_text else []
    return nums, consts

def _close(a, b, rel, absolute):
    return abs(a - b) <= max(rel * max(abs(a), abs(b)), absolute)

def _match_direct(claim, ctxset, rel):
    for v, dec in claim["variants"]:
        half = 1.0 * 10 ** (-dec)      # yuvarlama VEYA kırpma: son hanenin 1 birimi
        if dec == 0 and abs(v) < 10: half = 0.05          # küçük tam sayıda 0.5 tolerans tesadüfi eşleşme üretir
        for k in (1.0, 100.0, 0.01):
            for c in ctxset:
                cv = c * k
                # tolerans = iddianın yazıldığı son hanenin 1 birimi (yuvarlama/kırpma) ve/veya --rel-tol
                if _close(v, cv, rel, half * 1.0001): return cv
    return None

_DER_CACHE = {}
def _derived_tables(ctxlist, cap=260):
    import numpy as np
    key = id(ctxlist)
    if key in _DER_CACHE: return _DER_CACHE[key]
    vals = np.array(sorted(set(round(c, 8) for c in ctxlist if c != 0 and abs(c) < 1e12), key=lambda x: -abs(x)))
    if len(vals) > cap: vals = np.concatenate([vals[:cap // 2], vals[-cap // 2:]])
    A, B = vals[:, None], vals[None, :]
    same = (np.sign(A) == np.sign(B)) & (np.maximum(abs(A), abs(B)) <= 3 * np.minimum(abs(A), abs(B)))   # benzer büyüklük: fiyat-fiyat, oran-oran
    diff = abs(A - B)[same]; pct = (abs(A - B) / abs(B) * 100)[same]
    ratio = abs(A / B).ravel(); dr = (abs(A - B)[same][:, None] / abs(vals)[None, :]).ravel() if same.sum() * len(vals) < 6e6 else np.array([])
    t = {k: np.unique(np.round(v[np.isfinite(v)], 6)) for k, v in (("fark", diff), ("%fark", pct), ("oran", ratio), ("fark/x", dr))}
    _DER_CACHE.clear(); _DER_CACHE[key] = t; return t

def _hit(arr, target, tol):
    import numpy as np
    i = np.searchsorted(arr, target - tol); return i < len(arr) and arr[i] <= target + tol

def _match_derived(claim, ctxlist, rel, cap=260):
    """İddia = bağlamdaki iki (benzer büyüklükte) sayının farkı / % farkı mı? 'x' (kat) iddiaları için oran ve fark/ATR de denenir."""
    t = _derived_tables(ctxlist, cap)
    for v, dec in claim["variants"]:
        av = abs(v); tol = max(1.0 * 10 ** (-dec), 0.01 * av, rel * av)
        if _hit(t["fark"], av, tol) and av >= 5: return f"fark({av:g})"
        if claim["pct"] and _hit(t["%fark"], av, max(1.0 * 10 ** (-dec), 0.02 * av)): return f"%fark({av:g})"
        if claim["mult"]:
            for k in ("oran", "fark/x"):
                if _hit(t[k], av, max(1.0 * 10 ** (-dec), 0.03 * av)): return f"{k}({av:g})"
    return None

def validate(text, ctx_obj, prompt_text="", rel_tol=0.0, derived=True, label="", perturb=None):
    claims = extract_claims(text)
    if perturb is not None:   # null test: iddiaları kaydır -> hâlâ "eşleşirse" bu tesadüfi eşleşmedir
        for c in claims:
            f = perturb.choice([0.85, 0.88, 0.91, 0.94, 0.97, 1.03, 1.06, 1.09, 1.12, 1.15]); c["variants"] = [(v * f, d) for v, d in c["variants"]]
    nums, consts = build_context(ctx_obj, prompt_text); ctxset = sorted(set(nums))
    res = []
    for c in claims:
        m = _match_direct(c, ctxset, rel_tol); how = "eşleşti"; ev = m
        if m is None and consts:
            m2 = _match_direct(c, sorted(set(consts)), rel_tol)
            if m2 is not None: how, ev = "prompt_sabiti", m2
        if how == "eşleşti" and m is None:
            how, ev = "doğrulanamadı", None
            if derived:
                d = _match_derived(c, nums, rel_tol)
                if d: how, ev = "türetilmiş", d
        res.append({"raw": c["raw"], "durum": how, "kanıt": ev, "bağlam": c["ctx"], "pct": c["pct"]})
    return res

def summarize(res):
    n = len(res); cnt = {k: 0 for k in ("eşleşti", "türetilmiş", "prompt_sabiti", "doğrulanamadı", "seviye_yakın", "seviye_serbest")}
    for r in res: cnt[r["durum"]] += 1
    nt = n - cnt["seviye_yakın"] - cnt["seviye_serbest"]; cnt["toplam"] = nt; cnt["doğrulanamadı_oran"] = round(cnt["doğrulanamadı"] / nt, 4) if nt else None
    return cnt

def _stage_text(v):
    if v is None: return ""
    if isinstance(v, dict):                                    # stop/hedef/gerekçe/maddeler: ajanın seviyeleri de iddiadır
        parts = []
        for k, x in v.items():
            if k in SKIP_KEYS: continue
            if isinstance(x, (int, float)) and not isinstance(x, bool): continue    # stop/hedef -> ayrı 'seviye' kontrolü
            elif isinstance(x, list): parts.append(" ".join(map(str, x)))
            elif isinstance(x, str): parts.append(x)
        return "\n".join(parts)
    return str(v)

def _prompt_text():
    p = os.path.join(HERE, "agents.py")
    return open(p, encoding="utf-8").read() if os.path.exists(p) else ""

def check_output(obj, rel_tol=0.0, derived=True, prompt_text=None, stages=None, level_tol=0.003, perturb=None):
    """Bir outputs/*.json (debate modu: tech_data/sentiment_data/extras/memory/lessons_block içerir) için aşama bazlı doğrulama."""
    if not all(k in obj for k in ("tech_data", "sentiment_data")): return None
    ctx = {k: obj.get(k) for k in CONTEXT_FIELDS if obj.get(k) is not None}
    # Hakem/risk, işlem seviyelerini (stop/hedef) veriden seçer; ATR kural-risk sayıları da LLM'in gördüğü veridir (risk aşamasında ham veri verilir)
    pt = _prompt_text() if prompt_text is None else prompt_text
    out = {}
    m = re.search(r"Kapanış:\s*([\d.,]+)", str(obj.get("tech_data", ""))); close = _parse_variants(m.group(1))[0][0] if m and _parse_variants(m.group(1)) else None
    for st in (stages or STAGE_FIELDS):
        if st in obj and obj[st] is not None:
            ctx_st = dict(ctx)
            # Karar/risk aşamaları, komitenin stop/hedefini ve kendi seviyelerini girdi olarak görür; ayrıca %1 risk formülünden pozisyon büyüklüğü türetilir
            own = [v for src in (obj.get("hakem"), obj.get(st)) if isinstance(src, dict) for k, v in src.items() if k in ("stop", "hedef") and isinstance(v, (int, float))]
            if st in ("hakem", "risk_llm", "risk") and own: ctx_st["_kendi_ve_komite_seviyeleri"] = own
            if st in ("risk_llm", "risk") and close and own:
                ctx_st["_poz_formul"] = [round(100.0 * close / abs(close - x), 2) for x in own if abs(close - x) > 0] + [abs(close - x) for x in own]
            out[st] = validate(_stage_text(obj[st]), ctx_st, pt, rel_tol, derived, st, perturb)
            if isinstance(obj[st], dict):
                for k in ("stop", "hedef"):
                    v = obj[st].get(k)
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        nums, _ = build_context(ctx); cl = {"raw": f"{k}={v:g}", "variants": [(float(v), 0)], "pct": False, "mult": False, "ctx": f"{k}: {v}"}
                        m = None
                        for c in sorted(set(nums)):
                            if abs(c) > 0 and abs(v - c) <= level_tol * abs(v): m = c; break
                        out[st].append({"raw": cl["raw"], "durum": "seviye_yakın" if m is not None else "seviye_serbest", "kanıt": m, "bağlam": cl["ctx"], "pct": False})
    return out

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", help="tek outputs/*.json"); ap.add_argument("--scan", nargs="*", help="glob(lar): toplu ölçüm")
    ap.add_argument("--text"); ap.add_argument("--context-file")
    ap.add_argument("--rel-tol", type=float, default=0.0, help="ek göreli tolerans (varsayılan 0: yalnızca iddianın son hanesinin 1 birimi kadar yuvarlama toleransı; ör. 0.001 = %%0.1 ek)")
    ap.add_argument("--level-tol", type=float, default=0.003, help="stop/hedef karar seviyeleri için 'bir veri seviyesine yakınlık' toleransı")
    ap.add_argument("--null-test", action="store_true", help="iddiaları 5-20%% kaydırıp tesadüfi eşleşme oranını ölç"); ap.add_argument("--no-derived", action="store_true")
    ap.add_argument("--out"); ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    if a.text:
        ctx = open(a.context_file).read() if a.context_file else ""
        r = validate(a.text, ctx, "", a.rel_tol, not a.no_derived)
        for x in r: print(f"[{x['durum']}] {x['raw']}  <- ...{x['bağlam']}...  kanıt={x['kanıt']}")
        print(summarize(r)); return
    files = []
    if a.check: files = [a.check]
    if a.scan: [files.extend(sorted(glob.glob(g))) for g in a.scan]
    if not files: ap.print_help(); return
    agg = {}; per_file = {}; skipped = []
    for f in files:
        o = json.load(open(f)); import random
        r = check_output(o, a.rel_tol, not a.no_derived, level_tol=a.level_tol, perturb=random.Random(7) if a.null_test else None)
        if r is None: skipped.append(f); continue
        per_file[f] = {st: summarize(x) for st, x in r.items()}
        if a.check or a.verbose:
            print(f"== {f}")
            for st, x in r.items():
                print(f"  -- {st}: {summarize(x)}")
                for y in x:
                    if y["durum"] == "doğrulanamadı" or a.verbose: print(f"     [{y['durum']}] {y['raw']}   ...{y['bağlam']}...")
        for st, x in r.items():
            ag = agg.setdefault(st, {"eşleşti": 0, "türetilmiş": 0, "prompt_sabiti": 0, "doğrulanamadı": 0, "seviye_yakın": 0, "seviye_serbest": 0, "toplam": 0})
            for k, v in summarize(x).items():
                if k in ag: ag[k] += v
        r_all = agg.setdefault("TÜMÜ", {"eşleşti": 0, "türetilmiş": 0, "prompt_sabiti": 0, "doğrulanamadı": 0, "seviye_yakın": 0, "seviye_serbest": 0, "toplam": 0})
        for st, x in r.items():
            for k, v in summarize(x).items():
                if k in r_all: r_all[k] += v
    if a.scan:
        print(f"dosya: {len(files)}  doğrulanan: {len(per_file)}  atlanan (bağlam yok): {len(skipped)}")
        for st, ag in agg.items():
            ag["doğrulanamadı_oran"] = round(ag["doğrulanamadı"] / ag["toplam"], 4) if ag["toplam"] else None
            print(f"{st:16s} {ag}")
    if a.out:
        json.dump({"params": {"rel_tol": a.rel_tol, "derived": not a.no_derived}, "agg": agg, "per_file": per_file, "skipped": skipped}, open(a.out, "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__": main()
