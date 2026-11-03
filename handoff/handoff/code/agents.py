from llm import chat, parse_json

RULE = "Yalnızca verilen veriyi kullan, veri uydurma. Türkçe, kısa ve net yaz."
CTX = {"interval": "1d"}
# Formasyon bloğu (patterns.py, LLM'siz hesaplanır) için ortak kural; ek LLM çağrısı gerektirmez, mevcut istemlere eklenir.
PAT = ("Formasyon kuralları: yalnızca verideki 'Formasyonlar' bloğunda listelenenleri kullan; listelenmeyen mum/grafik/harmonik formasyonu, Fibonacci veya seviye UYDURMA. "
       "Tek formasyona güvenme: trend, seviye (destek/direnç, VWAP, POC), hacim ve göstergelerle çakışma (confluence) ara; en az 2 bağımsız kanıt yoksa ağırlığı düşük say, zayıf/çelişkili formasyonu yok say. "
       "Kullandığın formasyonun geçersizlik seviyesini söyle; 'boyun kırılmadı', 'retest bekleniyor', 'PRZ bölgesine X ATR kaldı' gibi durumları aynen koru (kırılmamışı kırılmış sayma).")
# Kullanıcı kritik seviyesi (keylevels.py, LLM'siz hesaplanır): verideki 'Kullanıcının kritik seviyesi' satırı için ortak kural; ek LLM çağrısı yok.
KL = ("Kritik seviye kuralı: veride 'Kullanıcının kritik seviyesi' satırı varsa o seviyeyi mutlaka değerlendir: 4s mum KAPANIŞININ seviyenin ALTINDA olması büyük bir AYI kırılım sinyalidir (düşüş yönünü güçlendirir, long'u zayıflatır); "
      "fitilin seviyenin altına inip kapanışın tekrar ÜSTÜNDE olması (tepki) BOĞA sinyalidir; yalnızca anlık/fitil dokunuşu kırılım sayılmaz. Seviyeye uzaklığı (%) ve son 4s kapanışın konumunu gerekçende belirt.")
HORIZON = {"15m": "birkaç saat", "1h": "1 gün", "4h": "2-3 gün", "1d": "1-2 hafta"}

def mode():
    iv = CTX["interval"]
    if iv == "1d":
        return f"Mum aralığı 1d (günlük), ufuk {HORIZON[iv]}. Swing/pozisyon bakışı."
    return (f"DİKKAT: Gün içi (intraday) analiz, mum aralığı {iv}, ufuk {HORIZON[iv]}. Göstergeler {iv} mumlarda hesaplandı "
            "(SMA200 = son 200 mum, günlük değil). Teknik yapı, funding oranı ve açık pozisyon (OI) değişimi öncelikli; "
            "haber/makro ve uzun vadeli duygu (Korku&Açgözlülük) ikincil. Komisyon ve kaymayı (slippage) unutma.")

def technical(tech):
    return chat(f"Sen bir kripto teknik analisti ve formasyon uzmanısın (grafik okuma, mum formasyonları, harmonikler, piyasa yapısı, uyumsuzluk). {RULE} {mode()} En fazla 190 kelime.",
                f"Veri:\n{tech}\n\nTrend (SMA50/200), momentum (RSI, MACD), volatilite (ATR) ve kritik destek/direnç seviyelerini yorumla. Hesaplanmış yapı seviyelerini (VWAP gün/hafta ±1σ, hacim profili POC/VAH/VAL/HVN/LVN, pivotlar, dolmamış FVG'ler, fraktal swing'ler) kullan; destek/direnci bu seviyelerden seç, uydurma; birden çok aracın çakıştığı bölgeleri (kesişim) öne çıkar. Fiyatın VWAP'a ve değer alanına göre konumunu belirt. Formasyon bloğunu (mum, grafik, harmonik, Fib, uyumsuzluk, yapı BOS/CHoCH, EMA/ADX/BB/Ichimoku/Supertrend) eleştirel kullan. {PAT} {KL} Son satıra yalnızca 'EĞİLİM: BOĞA' veya 'EĞİLİM: AYI' veya 'EĞİLİM: NÖTR' yaz.")

def sentiment(sent):
    return chat(f"Sen bir kripto duygu/türev piyasası analistisin. {RULE} {mode()} En fazla 150 kelime.",
                f"Veri:\n{sent}\n\nFunding, açık pozisyon, long/short oranı, taker akışı, likidasyonlar, emir defteri, hacim, zincir üstü/stablecoin verisi ve Korku&Açgözlülük endeksinden piyasa konumlanmasını ve duygu durumunu yorumla. Aşırılık var mı? Son satıra yalnızca 'EĞİLİM: BOĞA' veya 'EĞİLİM: AYI' veya 'EĞİLİM: NÖTR' yaz.")

def bull(tech_r, sent_r):
    return chat(f"Sen BOĞA tarafını savunan araştırmacısın. {RULE} {mode()} En fazla 120 kelime.",
                f"Teknik rapor:\n{tech_r}\n\nDuygu raporu:\n{sent_r}\n\nAlım için en güçlü 3 argümanı ver. Sayıları ham veriyle birebir doğru aktar (ör. MACD histogramı hangi yönde değişti).")

def bear(tech_r, sent_r, bull_r):
    return chat(f"Sen AYI tarafını savunan araştırmacısın. {RULE} {mode()} En fazla 120 kelime.",
                f"Teknik rapor:\n{tech_r}\n\nDuygu raporu:\n{sent_r}\n\nBoğanın argümanları:\n{bull_r}\n\nGörevin KARŞI tarafı savunmak: boğaya katılma. Satış/kaçınma için en güçlü 3 argümanı ver ve boğanın en zayıf iddiasını veriyle çürüt.")

def judge(tech, tech_r, sent_r, bull_r, bear_r, memory="Geçmiş karar yok (hafıza boş).", lessons=""):
    txt = chat(f"Sen tarafsız bir yatırım komitesi başkanısın. {RULE} {mode()}",
               f"Ham veri:\n{tech}\n\nHafıza (geçmiş kararların ve ajan isabetleri; az örnekse fazla önemseme):\n{memory}\n\n{lessons + chr(10) + chr(10) if lessons else ''}Teknik:\n{tech_r}\n\nDuygu:\n{sent_r}\n\nBoğa:\n{bull_r}\n\nAyı:\n{bear_r}\n\n"
               f"{HORIZON[CTX['interval']]} ufku için karar ver. Stop/hedefi ham verideki hesaplanmış yapı seviyeleriyle (swing, FVG, VWAP, POC/VAH/VAL, pivot, formasyon geçersizlik/hedef seviyeleri) tutarlı seç. {PAT} {KL} SADECE şu JSON'u döndür (anahtarlar Türkçe ve aynen böyle): "
               '{"karar":"BUY|SELL|HOLD","guven":0-100,"stop":<fiyat>,"hedef":<fiyat>,"gerekce":"<en fazla 60 kelime>","maddeler":["<en fazla 10 kelimelik tam cümle>","<...>","<...>"]}', max_tokens=1500, role="deep")
    return txt, parse_json(txt)

def risk(tech, verdict):
    txt = chat(f"Sen risk yöneticisisin. {RULE} {mode()}",
               f"Ham veri:\n{tech}\n\nKomite kararı:\n{verdict}\n\n"
               "ATR'ye göre stop mantıklı mı? 10.000 $'lık örnek portföyde, işlem başına en fazla %1 risk ile pozisyon büyüklüğü öner. "
               'SADECE JSON (anahtarlar Türkçe ve aynen böyle): {"onay":true|false,"stop":<fiyat>,"pozisyon_usd":<sayı>,"not":"<en fazla 50 kelime>"}', max_tokens=1200, role="deep")
    return txt, parse_json(txt)


# --- Çoklu zaman dilimi (MTF): 4h trend ajanı + 1h/15m giriş ajanı; yalnızca hizalıysa sinyal ---
def trend_4h(tech4h, deriv, lessons=""):
    txt = chat(f"Sen 4h trend analistisin. {RULE} Mum aralığı 4h.",
               f"4h veri:\n{tech4h}\n\nTürev/akış:\n{deriv}\n\n{lessons + chr(10) + chr(10) if lessons else ''}Ana trendi belirle. Yapıyı da dikkate al: fiyatın haftalık VWAP ve hacim profili değer alanına göre konumu, haftalık pivot, dolmamış FVG ve swing seviyeleri; piyasa yapısı (HH/HL, BOS/CHoCH), EMA/ADX/Supertrend/Ichimoku ve büyük formasyonlar (çift tepe/dip, OBO, üçgen, kama, harmonik). {PAT} {KL} "
               'SADECE JSON (anahtarlar aynen): {"trend":"YUKARI|ASAGI|YATAY","guven":0-100,"gerekce":"<40 kelime>"}', max_tokens=1000, role="deep")
    return txt, parse_json(txt)

def entry_ltf(tech_ltf, deriv, trend, iv, lessons=""):
    txt = chat(f"Sen {iv} giriş zamanlaması uzmanısın. {RULE} Gün içi; komisyon+kayma (~%0,3 gidiş-dönüş) maliyetini hesaba kat.",
               f"Üst zaman dilimi (4h) trend kararı: {trend}\n\n{iv} veri:\n{tech_ltf}\n\nTürev/akış/emir defteri:\n{deriv}\n\n{lessons + chr(10) + chr(10) if lessons else ''}"
               'Şimdi giriş var mı? Yakın yapı seviyelerine (swing, FVG, VWAP, POC/VAH/VAL, pivot) bak: hemen önünde güçlü direnç/destek varsa ve hedefe yer yoksa girme. Giriş tetikleyicisi olarak mum formasyonunu (konum+hacim), BOS/CHoCH, likidite süpürme, uyumsuzluk ve harmonik PRZ bölgesini kullan; çakışma yoksa YOK de. ' + PAT + ' ' + KL + ' SADECE JSON (anahtarlar aynen): {"giris":"LONG|SHORT|YOK","guven":0-100,"stop":<fiyat>,"hedef":<fiyat>,"gerekce":"<40 kelime>"}', max_tokens=1000, role="deep")
    return txt, parse_json(txt)
