"""Sağlayıcı zinciri + otomatik yedeğe geçiş (config.json -> "providers").
Sıra: Gemini (analist: flash-lite, hakem/risk: gemini-3-flash-preview) -> OpenRouter ücretsiz -> (isteğe bağlı) yerel Ollama.
429/kota, 5xx, zaman aşımı veya boş yanıtta sıradaki modele/sağlayıcıya geçer. Günlük kotası biten sağlayıcı oturum boyunca atlanır.
Her çağrıda hangi sağlayıcı/modelin yanıt verdiği CALLS["log"]'a yazılır."""
import re, os, time, json, re
from openai import OpenAI, APIStatusError, APITimeoutError, APIConnectionError

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json")))
PROVIDERS = [p for p in CFG["providers"] if p.get("enabled", True)]
if os.environ.get("CA_PROVIDERS"):  # ör. CA_PROVIDERS=openrouter,gemini
    order = os.environ["CA_PROVIDERS"].split(","); PROVIDERS = [p for n in order for p in CFG["providers"] if p["name"] == n]
MODEL = " -> ".join(f"{p['name']}" for p in PROVIDERS)   # bilgi amaçlı
CALLS = {"n": 0, "log": []}
_clients, _last, _dead = {}, {}, set()

class AllProvidersExhausted(SystemExit): pass
class EmptyResponse(Exception): pass

def _load_env(p):
    if p.get("key_env") and not os.environ.get(p["key_env"]) and p.get("env_file") and os.path.exists(p["env_file"]):
        for line in open(p["env_file"]):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1); os.environ.setdefault(k, v.strip().strip('"'))

def _client(p):
    if p["name"] not in _clients:
        _load_env(p); key = os.environ.get(p["key_env"]) if p.get("key_env") else "ollama"
        if not key: return None
        _clients[p["name"]] = OpenAI(base_url=p["base_url"], api_key=key, timeout=p.get("timeout_s", 120), max_retries=0)
    return _clients[p["name"]]

def _extra(p, attempt):
    if p.get("reasoning") == "reasoning_effort": return {"reasoning_effort": "low"}, {}
    if p.get("reasoning") == "openrouter": return {}, {"reasoning": {"effort": "low"} if attempt == 0 else {"enabled": False}}
    return {}, {}

def _mock(system, user):
    """CA_DRY_RUN=1: LLM çağırmadan boru hattını test etmek için SAHTE yanıt. Sonuç değildir."""
    if "JSON" in user and "onay" in user: return '{"onay":true,"stop":null,"pozisyon_usd":0,"not":"DRY-RUN sahte yanıt"}'
    if "JSON" in user and '"trend"' in user: return '{"trend":"YUKARI","guven":50,"gerekce":"DRY-RUN"}'
    if "JSON" in user and '"giris"' in user: return '{"giris":"LONG","guven":50,"gerekce":"DRY-RUN"}'
    if "JSON" in user: return '{"karar":"BUY","guven":50,"stop":null,"hedef":null,"gerekce":"DRY-RUN sahte yanıt"}'
    return "DRY-RUN sahte metin (LLM çağrılmadı).\nEĞİLİM: NÖTR"

DEADF = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs", ".cache", "llm_dead.json")
def _load_dead():
    try:
        d = json.load(open(DEADF)); t = time.time()
        for k, until in d.items():
            if until > t: _dead.add(k)
    except Exception: pass
def _mark_dead(key, e):
    """Günlük kota bitti: süreçler arası kalıcı kaydet (retryDelay kadar, yoksa 6 saat)."""
    _dead.add(key)
    m = re.search(r"retryDelay'?\"?\s*:\s*'?\"?(\d+)s", str(e)); secs = int(m.group(1)) if m else 6 * 3600
    try:
        d = json.load(open(DEADF)) if os.path.exists(DEADF) else {}
        d[key] = time.time() + secs; os.makedirs(os.path.dirname(DEADF), exist_ok=True); json.dump(d, open(DEADF, "w"))
    except Exception: pass
    print(f"  [kota] {key} günlük limit -> {secs//60} dk atlanacak")

def _is_daily(e):
    s = str(e).lower()
    return any(k in s for k in ("per-day", "perday", "per day", "free-models-per-day", "requests per day", "daily"))

def chat(system, user, model=None, max_tokens=1200, retries=2, role="quick"):
    if os.environ.get("CA_DRY_RUN") == "1": return _mock(system, user)
    _load_dead()
    max_tokens = max(max_tokens, 4000)   # akıl yürüten modeller token'ın bir kısmını düşünmeye harcıyor
    errors = []
    for p in PROVIDERS:
        if p["name"] in _dead: continue
        c = _client(p)
        if c is None: errors.append(f"{p['name']}: anahtar yok"); continue
        models = [model] if model else [p["models"][role]] + p.get("fallback_models", {}).get(role, [])
        for m in models:
            if f"{p['name']}/{m}" in _dead: continue
            for attempt in range(retries):
                wait = p.get("min_interval_s", 0) - (time.time() - _last.get(p["name"], 0))
                if wait > 0: time.sleep(wait)
                _last[p["name"]] = time.time(); CALLS["n"] += 1; t0 = time.time()
                try:
                    kw, extra = _extra(p, attempt)
                    r = c.chat.completions.create(model=m, temperature=0.3, max_tokens=max_tokens,
                                                  messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                                  extra_body=extra or None, **kw)
                    txt = (r.choices[0].message.content or "").strip()
                    if not txt: raise EmptyResponse(f"boş yanıt (finish_reason={r.choices[0].finish_reason})")
                    CALLS["log"].append({"provider": p["name"], "model": m, "role": role, "s": round(time.time() - t0, 1), "ok": True})
                    return txt
                except APIStatusError as e:
                    msg = f"{p['name']}/{m}: HTTP {e.status_code} {str(e)[:160]}"
                    CALLS["log"].append({"provider": p["name"], "model": m, "role": role, "ok": False, "err": msg[:200]})
                    errors.append(msg); print("  [yedek]", msg[:200])
                    if e.status_code == 429 and "PerModel" in str(e) and "PerDay" in str(e):
                        _mark_dead(f"{p['name']}/{m}", e); break          # Gemini: model başına günlük kota -> yalnız bu modeli atla
                    if e.status_code == 402 or (e.status_code == 429 and _is_daily(e)):
                        _mark_dead(p["name"], e); break                   # günlük kota/kredi bitti -> sağlayıcıyı atla
                    if e.status_code in (400, 404): _dead.add(f"{p['name']}/{m}"); break   # model yok -> sonraki model
                    if e.status_code == 429: time.sleep(min(20, 5 * (attempt + 1)))       # dakikalık limit -> kısa bekle
                except (APITimeoutError, APIConnectionError, EmptyResponse) as e:
                    msg = f"{p['name']}/{m}: {type(e).__name__} {str(e)[:120]}"
                    CALLS["log"].append({"provider": p["name"], "model": m, "role": role, "ok": False, "err": msg})
                    errors.append(msg); print("  [yedek]", msg)
                    if isinstance(e, APITimeoutError): break
            if p["name"] in _dead: break
    raise AllProvidersExhausted("Tüm sağlayıcılar tükendi/başarısız: " + " | ".join(errors[-6:]))

def last_provider():
    ok = [x for x in CALLS["log"] if x.get("ok")]
    return f"{ok[-1]['provider']}/{ok[-1]['model']}" if ok else None

def parse_json(txt):
    m = re.search(r"\{.*\}", txt, re.S)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None
