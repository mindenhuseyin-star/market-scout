import os, json, asyncio, httpx, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from html import unescape
import re

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "user/market-scout")

RSS_FEEDS = [
    ("TechCrunch", "https://techcrunch.com/feed/"),
    ("TechCrunch Startups", "https://techcrunch.com/category/startups/feed/"),
    ("The Next Web", "https://thenextweb.com/feed/"),
    ("Hacker News", "https://news.ycombinator.com/rss"),
]

TURKEY_CONTEXT = """
TURKIYE EKONOMIK VE PAZAR BAGLAMI (her analizde dikkate al):

Ekonomik gercekler:
- TL volatilitesi nedeniyle dolar/euro gelirli veya dolar korumasI saglayan is modelleri cok daha cazip
- Yuksek enflasyon ortaminda maliyet dusuren SaaS ve otomasyon cozumleri hizla benimseniyor
- KOBIlerde dijitallesme hala dusuk, devlet tesvikleri var (KOSGEB, TUBITAk destekleri)

Pazar avantajlari:
- 85 milyon nufus, medyan yas 32 -- genc ve mobil odakli tuketici
- Mobil penetrasyon %80+ -- mobil-first urunler icin ideal
- E-ticaret buyumesi yillik %30+ -- cross-border ve marketplace modeller guclu
- Turkiye uretim ussu -- lojistik, tedarik zinciri, ihracat teknolojileri buyuk firsat

Dikkat edilmesi gereken riskler:
- Fintech: BDDK duzenlemeleri katı, lisans sureci uzun
- Saglik: Saglik Bakanligi onayları zorunlu, veri gizliligi hassas
- Egitim: MEB duzenlemeleri, akreditasyon
- Buyuk oyuncular: Trendyol, Getir, Hepsiburada, Logo, Parasut, Enpara -- bunlar varsa acik sormak lazim
- Sermaye: Turkiye VC ekosistemi buyuyor ama erken asamada sermaye hala kisitli

Zamanlama sinyalleri -- su an ozellikle guclu alanlar:
- AI destekli B2B SaaS (KOBIler icin ucuz otomasyon)
- E-ihracat altyapisi ve cross-border lojistik
- Tedarik zinciri gorunurlugu
- Ikinci el ve cirkuler ekonomi platformlari
- Kucuk isletmeler icin finansal yonetim araclari
"""

ANALYST_PROMPT = """Sen global teknoloji, startup ve e-ticaret trendlerini takip eden kidemli bir pazar arastirma analisti ve VC yatirim danismanisın.

Gorev: Son 48 saatte toplanan global haberleri analiz ederek Turkiye pazari icin potansiyel is firsatlarini cikar.
Amac haber ozeti degil; dunyada basarili olmaya baslayan fakat Turkiye'de henuz yayginlasmamis is modellerini yakalamak.

TREND YOGUNLUGU KURALI -- cok onemli:
- Ayni tema 3+ farkli haberden gucleniyorsa bu guclu sinyal, skoru +10 artir
- Ayni tema 2 haberden gucleniyorsa orta sinyal, skoru +5 artir
- Tek haberden gelen fikir zayif sinyal olarak isaretle

ANALIZ KRITERLERI:
1. Gercek bir probleme cozum getiriyor mu?
2. Net bir aci noktasi var mi?
3. ABD, Avrupa veya Asya'da traction almiş mi?
4. Turkiye'de benzer guclu oyuncu var mi? Varsa neden yetersiz?
5. Turkiye'ye uyarlanabilir mi?
6. MVP 30-60 gunde kurulabilir mi?
7. B2B, SaaS, marketplace, e-ticaret, lojistik, finans, AI agent alaninda gelir potansiyeli var mi?
8. Gecici hype mi yoksa kalici ihtiyac mi?

KIRMIZI BAYRAK KONTROLLERI -- her firsat icin zorunlu:
- Turkiye'de regülasyon riski var mi? (fintech=yuksek, saglik=yuksek, egitim=orta)
- Trendyol, Getir, Hepsiburada, Logo, Parasut gibi buyuk oyuncu bu alana girebilir mi?
- Sermaye yogun mu? (ilk yil kac dolar gerekir tahmini ver)
- Referans musteri bulmak zor mu?
- Turkiye'de benzer girisim var ve buyuyemiyorsa neden buyuyemedigi?

ZAMANLAMA ANALIZI:
- Bu model 6-12 ay once de ayni gucte miydi?
- Su an neden daha dogru zaman?
- Turkiye'ye gore erken mi, tam zamani mi, gec mi?"""

CONTEXT_PROMPT = """Asagidaki firsatlari Turkiye ekonomik ve pazar baglaminda yeniden degerlendir.

""" + TURKEY_CONTEXT + """

Her firsat icin su ek alanlari doldur:
- tl_advantage: TL volatilitesi veya Turkiye ekonomisi bu modeli nasil avantajli/dezavantajli kiliyor?
- timing: Turkiye icin erken mi, tam zamani mi, gec mi? Neden?
- big_player_risk: Hangi buyuk Turkiye sirketi bu alana girebilir?
- red_flags: Kirmizi bayraklar listesi
- signal_strength: Trend kac farkli kaynaktan geliyor? (guclu/orta/zayif)
- capital_estimate: Ilk MVP icin tahmini sermaye ihtiyaci (USD)

Ayni JSON array formatini koru, her objeye bu yeni alanlari ekle. Baska hicbir sey yazma."""

FILTER_PROMPT = """Asagidaki firsatlari sert filtreden gecir.

Su kriterlerden en az 3 tanesini karsilamayan fikirleri cikar:
1. Turkiye'de acik pazar boslugu var
2. MVP 30-60 gunde kurulabilir
3. B2B veya SaaS gelir modeli var
4. E-ticaret, operasyon, finans, lojistik veya AI verimliligi alanina dokunuyor
5. Globalde guclu sinyal var (yatirim, kullanici artisi, medya, acik kaynak)
6. Buyuk oyuncularin henuz tam cozemedigi probleme odaklaniyor

Ek eleme kurallari:
- Sadece hype olan, temel problemi net olmayan fikirleri ele
- Turkiye'de zaten guclu oyuncu varsa ve acik bosluk yoksa ele
- Sermaye ihtiyaci ilk yil 500K USD uzeri ve VC olmadan yapilmasi imkansiz ise ele
- Regülasyon riski cok yuksek ve asılması yillar alacaksa ele

Kalan firsatlari en gucludan en zayifa sirala.
Ayni JSON array formatinda dondur. Baska hicbir sey yazma."""

def clean(text):
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()[:200]

async def fetch_rss(client, name, url):
    try:
        r = await client.get(url, timeout=15, follow_redirects=True)
        root = ET.fromstring(r.text)
        items = []
        keywords = ["startup","funding","raises","series","launch","million",
                    "billion","saas","marketplace","fintech","acquired","yc",
                    "health","edtech","delivery","app","platform","ai","agent",
                    "open source","automation","logistics","b2b","ecommerce",
                    "supply chain","payments","revenue","growth","tool"]
        for item in root.iter("item"):
            title = clean(item.findtext("title",""))
            desc  = clean(item.findtext("description",""))
            if not title: continue
            if any(k in (title+desc).lower() for k in keywords):
                items.append({"title": title, "desc": desc, "source": name})
        print("OK " + name + ": " + str(len(items)))
        return items
    except Exception as e:
        print("ERR " + name + ": " + str(e))
        return []

async def fetch_all_news():
    print("Fetching RSS feeds...")
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        results = await asyncio.gather(*[fetch_rss(client, n, u) for n, u in RSS_FEEDS])
    all_items, seen = [], set()
    for items in results:
        for item in items:
            if item["title"] not in seen:
                seen.add(item["title"])
                all_items.append(item)
    print("Total: " + str(len(all_items)) + " articles")
    return all_items[:40]

async def gemini(prompt_text, max_tokens=4000):
    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY
    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, json={
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {"temperature": 0.4, "maxOutputTokens": max_tokens}
        })
    body = r.json()
    if "error" in body:
        raise ValueError("Gemini error: " + str(body["error"]))
    return body["candidates"][0]["content"]["parts"][0]["text"]

def extract_json_array(text):
    text = re.sub(r"```json|```", "", text).strip()
    s, e = text.find("["), text.rfind("]") + 1
    if s != -1 and e > s:
        return json.loads(text[s:e])
    s2, e2 = text.find("{"), text.rfind("}") + 1
    if s2 != -1:
        data = json.loads(text[s2:e2])
        return data.get("opportunities", [])
    return []

async def analyze(articles):
    today = datetime.now().strftime("%d %B %Y")
    news_text = "\n".join("- [" + a["source"] + "] " + a["title"] + " -- " + a["desc"] for a in articles)

    # KATMAN 1: Analist
    print("Katman 1: Analist calisiyor...")
    step1 = (
        ANALYST_PROMPT + "\n\n"
        "Bugun: " + today + "\n\n"
        "Haberler:\n" + news_text + "\n\n"
        "JSON formatinda dondur, baska hicbir sey yazma:\n"
        '{"date":"' + today + '","opportunities":['
        '{"name":"Firsat Adi",'
        '"emoji":"tek emoji",'
        '"sector":"Sektor",'
        '"score":82,'
        '"signal_count":2,'
        '"global_trend":"Global trend aciklamasi",'
        '"problem":"Cozulen problem",'
        '"tr_gap":"Turkiyedeki bosluk",'
        '"tr_idea":"Turkiyeye uygulama fikri",'
        '"mvp":"Ilk MVP nasil kurulur",'
        '"target":"Hedef musteri",'
        '"revenue":"Gelir modeli",'
        '"competition":"Rekabet durumu",'
        '"risks":"Riskler",'
        '"timing_note":"Neden simdi dogru zaman",'
        '"inspired_by":"Kaynak haber"}'
        "]}"
    )
    raw1 = await gemini(step1)
    raw1 = re.sub(r"```json|```", "", raw1).strip()
    s, e = raw1.find("{"), raw1.rfind("}") + 1
    if s == -1:
        raise ValueError("Katman1 JSON yok: " + raw1[:200])
    data = json.loads(raw1[s:e])
    opps = data.get("opportunities", [])
    print("Katman 1 tamamlandi: " + str(len(opps)) + " firsat")

    # KATMAN 2: Turkiye baglamı + kirmizi bayraklar
    print("Katman 2: Turkiye baglam analizi...")
    step2 = (
        CONTEXT_PROMPT + "\n\n"
        "Firsatlar:\n" + json.dumps(opps, ensure_ascii=False) + "\n\n"
        "Her objeye su alanlari ekleyerek ayni JSON array formatinda dondur:\n"
        "tl_advantage, timing, big_player_risk, red_flags, signal_strength, capital_estimate"
    )
    raw2 = await gemini(step2)
    enriched = extract_json_array(raw2)
    if enriched:
        opps = enriched
    print("Katman 2 tamamlandi: " + str(len(opps)) + " firsat zenginlestirildi")

    # KATMAN 3: Sert filtre
    print("Katman 3: Sert filtre calisiyor...")
    step3 = (
        FILTER_PROMPT + "\n\n"
        "Firsatlar:\n" + json.dumps(opps, ensure_ascii=False)
    )
    raw3 = await gemini(step3)
    filtered = extract_json_array(raw3)
    if filtered:
        opps = filtered
    print("Katman 3 tamamlandi: " + str(len(opps)) + " firsat filtreden gecti")

    data["opportunities"] = opps
    return data

COLORS = {
    "fintech": "#3B82F6", "e-ticaret": "#F97316", "marketplace": "#F97316",
    "ecommerce": "#F97316", "yemek": "#EF4444", "delivery": "#EF4444",
    "saas": "#8B5CF6", "b2b": "#8B5CF6", "health": "#10B981", "saglik": "#10B981",
    "egitim": "#F59E0B", "education": "#F59E0B", "lojistik": "#06B6D4",
    "ai": "#EC4899", "logistics": "#06B6D4", "otomasyon": "#EC4899",
}

def clr(s):
    s = s.lower()
    for k, v in COLORS.items():
        if k in s: return v
    return "#6366F1"

def sbar(score, c):
    f = round(score / 10)
    b = "\u2588" * f + "\u2591" * (10 - f)
    return '<span style="color:' + c + ';letter-spacing:2px;font-family:monospace">' + b + '</span> <strong style="color:' + c + '">' + str(score) + '%</strong>'

def signal_badge(strength):
    if not strength: return ""
    s = str(strength).lower()
    if "guclu" in s or "strong" in s or "3" in s:
        return '<span class="sig sig-strong">GUCLU SINYAL</span>'
    elif "orta" in s or "medium" in s or "2" in s:
        return '<span class="sig sig-medium">ORTA SINYAL</span>'
    return '<span class="sig sig-weak">ZAYIF SINYAL</span>'

def red_flag_html(flags):
    if not flags: return ""
    return '<div class="rf"><div class="dl">Kirmizi Bayraklar</div>' + str(flags) + '</div>'

def build_html(data, history):
    opps = data.get("opportunities", [])
    today = data.get("date", "")

    cards = ""
    for rank, o in enumerate(opps, 1):
        c = clr(o.get("sector", ""))
        score = o.get("score", 0)
        cards += (
            '<div class="card" style="border-left:4px solid ' + c + '">'
            '<div class="ch">'
            '<span class="rank" style="background:' + c + '22;color:' + c + '">#' + str(rank) + '</span>'
            '<span class="ce">' + o.get("emoji","") + '</span>'
            '<div style="flex:1">'
            '<div class="cn">' + o.get("name","") + '</div>'
            '<div class="co">' + o.get("global_trend","")[:90] + '...</div>'
            '</div>'
            '<div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px;flex-shrink:0">'
            '<span class="badge" style="background:' + c + '20;color:' + c + ';border:1px solid ' + c + '40">' + o.get("sector","") + '</span>'
            + signal_badge(o.get("signal_strength","")) +
            '</div>'
            '</div>'
            '<div class="sr"><span class="sl">Firsat Skoru</span>' + sbar(score, c) + '</div>'
            '<div class="ins">Kaynak: <em>' + o.get("inspired_by","") + '</em></div>'
            + red_flag_html(o.get("red_flags","")) +
            '<details><summary>Tam analizi gor</summary><div class="dg">'
            '<div class="db full"><div class="dl">Cozulen Problem</div>' + o.get("problem","") + '</div>'
            '<div class="db full"><div class="dl">Turkiyedeki Bosluk</div>' + o.get("tr_gap","") + '</div>'
            '<div class="db full"><div class="dl">Uygulama Fikri</div>' + o.get("tr_idea","") + '</div>'
            '<div class="db"><div class="dl">Ilk MVP</div>' + o.get("mvp","") + '</div>'
            '<div class="db"><div class="dl">Hedef Musteri</div>' + o.get("target","") + '</div>'
            '<div class="db"><div class="dl">Gelir Modeli</div>' + o.get("revenue","") + '</div>'
            '<div class="db"><div class="dl">Rekabet</div>' + o.get("competition","") + '</div>'
            '<div class="db"><div class="dl">TL / Ekonomi Etkisi</div>' + o.get("tl_advantage","") + '</div>'
            '<div class="db"><div class="dl">Zamanlama</div>' + o.get("timing","") + '' + o.get("timing_note","") + '</div>'
            '<div class="db"><div class="dl">Buyuk Oyuncu Riski</div>' + o.get("big_player_risk","") + '</div>'
            '<div class="db"><div class="dl">Tahmini Sermaye</div>' + str(o.get("capital_estimate","")) + '</div>'
            '<div class="db"><div class="dl">Genel Riskler</div>' + o.get("risks","") + '</div>'
            '</div></details></div>'
        )

    hist_html = ""
    for h in reversed(history[-20:]):
        opps_h = h.get("opportunities",[])[:3]
        tags = "".join(
            '<span class="htag" style="color:' + clr(o.get("sector","")) + '">'
            + o.get("emoji","") + " " + o.get("name","") + '</span>'
            for o in opps_h
        )
        hist_html += '<div class="hrow"><span class="hd">' + h.get("date","") + '</span><span class="ht">' + tags + '</span></div>'

    avg  = round(sum(o.get("score",0) for o in opps) / max(len(opps),1))
    top  = opps[0] if opps else {}
    high = len([o for o in opps if o.get("score",0) >= 75])

    return """<!DOCTYPE html><html lang="tr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Scout TR -- """ + today + """</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a12;color:#e0e0f0;font-family:system-ui,sans-serif;padding-bottom:60px}
header{background:#0f0f1e;border-bottom:1px solid #1e1e2e;padding:16px 20px;position:sticky;top:0;z-index:10}
.hi{max-width:920px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
h1{font-family:monospace;font-size:18px;color:#f0f0f8}.sub{font-size:11px;color:#444;margin-top:2px}
.dbadge{background:#1e1e2e;border:1px solid #2a2a3e;border-radius:8px;padding:5px 12px;font-family:monospace;font-size:11px;color:#666}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#10B981;box-shadow:0 0 6px #10B981;margin-right:5px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
main{max-width:920px;margin:0 auto;padding:16px 20px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px}
.stat{background:#13131f;border:1px solid #1e1e2e;border-radius:10px;padding:12px;text-align:center}
.sv{font-family:monospace;font-size:17px;font-weight:700;color:#f0f0f8}
.sl2{font-size:10px;color:#444;margin-top:3px;text-transform:uppercase;letter-spacing:.08em}
.stitle{font-family:monospace;font-size:10px;color:#333;text-transform:uppercase;letter-spacing:.12em;margin-bottom:10px}
.src{font-size:11px;color:#3B82F6;background:#3B82F610;border:1px solid #3B82F620;border-radius:8px;padding:7px 12px;margin-bottom:14px}
.card{background:#13131f;border-radius:12px;padding:14px;margin-bottom:12px;border:1px solid #1e1e2e}
.ch{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px}
.rank{font-family:monospace;font-size:11px;font-weight:700;padding:3px 7px;border-radius:6px;flex-shrink:0;margin-top:2px}
.ce{font-size:22px;line-height:1.4;flex-shrink:0}
.cn{font-family:monospace;font-size:13px;font-weight:700;margin-bottom:3px}
.co{font-size:12px;color:#666;line-height:1.4}
.badge{font-size:10px;font-weight:700;padding:3px 8px;border-radius:99px;white-space:nowrap}
.sig{font-size:9px;font-weight:700;padding:2px 7px;border-radius:99px;letter-spacing:.06em}
.sig-strong{background:#10B98120;color:#10B981;border:1px solid #10B98140}
.sig-medium{background:#F59E0B20;color:#F59E0B;border:1px solid #F59E0B40}
.sig-weak{background:#6B728020;color:#6B7280;border:1px solid #6B728040}
.sr{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-size:11px;color:#444}
.sl{text-transform:uppercase;letter-spacing:.08em}
.ins{font-size:11px;color:#555;margin-bottom:6px;padding:6px 10px;background:#0d0d1a;border-radius:6px;font-style:italic}
.rf{font-size:11px;color:#EF4444;padding:6px 10px;background:#EF444408;border-radius:6px;border:1px solid #EF444420;margin-bottom:8px}
details summary{font-size:12px;color:#3B82F6;cursor:pointer;padding:6px 0;list-style:none;font-weight:600}
details summary::-webkit-details-marker{display:none}
details[open] summary{margin-bottom:10px}
.dg{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.db{background:#0d0d1a;border-radius:8px;padding:10px 12px;font-size:12px;color:#bbb;line-height:1.6}
.db.full{grid-column:1/-1}
.dl{font-size:10px;color:#555;font-weight:700;margin-bottom:5px;text-transform:uppercase;letter-spacing:.06em}
.hist{background:#13131f;border:1px solid #1e1e2e;border-radius:12px;padding:14px;margin-top:18px}
.hrow{padding:7px 0;border-bottom:1px solid #1a1a2a;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.hrow:last-child{border:none}
.hd{font-family:monospace;font-size:10px;color:#333;min-width:80px;flex-shrink:0}
.ht{display:flex;gap:8px;flex-wrap:wrap}.htag{font-size:11px}
footer{text-align:center;padding:28px;font-size:10px;color:#1e1e2e;font-family:monospace}
@media(max-width:600px){.dg{grid-template-columns:1fr}.db.full{grid-column:1}}
</style></head><body>
<header><div class="hi">
  <div><h1><span class="dot"></span>Market Scout TR</h1>
  <div class="sub">3 katmanli VC kalitesinde analiz -- Analist + Baglam + Sert Filtre</div></div>
  <div class="dbadge">""" + today + """</div>
</div></header>
<main>
  <div class="stats">
    <div class="stat"><div class="sv">""" + str(avg) + """%</div><div class="sl2">Ort. Skor</div></div>
    <div class="stat"><div class="sv">""" + top.get("emoji","") + " " + top.get("name","").split("/")[0][:14] + """</div><div class="sl2">Gunun Firsati</div></div>
    <div class="stat"><div class="sv">""" + str(high) + """</div><div class="sl2">75%+ Skor</div></div>
  </div>
  <div class="src">Katman 1: Analist -- Katman 2: Turkiye Baglamı + Kirmizi Bayraklar -- Katman 3: Sert Filtre -- """ + str(len(opps)) + """ firsat gecti</div>
  <div class="stitle">Bugünün Firsatlari -- En Gucluden En Zayifa</div>
  """ + cards + """
  <div class="hist">
    <div class="stitle" style="margin-bottom:12px">Gecmis Taramalar</div>
    """ + (hist_html or '<div style="color:#222;font-size:12px">Henuz gecmis yok.</div>') + """
  </div>
</main>
<footer>Market Scout TR -- Her sabah 09:00 -- 3 katmanli AI analizi -- Gemini 2.0 Flash</footer>
</body></html>"""

async def send_telegram(data, page_url):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured, skipping.")
        return
    opps = data.get("opportunities", [])
    lines = ["Market Scout TR -- " + data.get("date","") + "\n3 katmanli filtreli analiz\n"]
    for i, o in enumerate(opps[:3], 1):
        f = round(o.get("score",0) / 10)
        bar = "\u2588" * f + "\u2591" * (10 - f)
        lines.append(str(i) + ". " + o.get("emoji","") + " " + o.get("name","") + " -- " + str(o.get("score",0)) + "%")
        lines.append(bar)
        lines.append(o.get("tr_gap","")[:100])
        lines.append("")
    lines.append("Detaylar: " + page_url)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines)},
        )
    print("Telegram OK" if r.status_code == 200 else "Telegram ERR: " + r.text[:80])

async def main():
    print("Market Scout TR -- " + datetime.now().strftime("%d.%m.%Y %H:%M"))
    articles = await fetch_all_news()
    data = await analyze(articles)

    os.makedirs("docs", exist_ok=True)
    hist_path = "docs/history.json"
    history = json.load(open(hist_path)) if os.path.exists(hist_path) else []
    history = [h for h in history if h.get("date") != data.get("date")]
    history.append(data)
    history = history[-30:]

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(build_html(data, history[:-1]))
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print("Saved docs/index.html")

    u, repo = GITHUB_REPO.split("/")
    await send_telegram(data, "https://" + u + ".github.io/" + repo)
    print("Done!")

if __name__ == "__main__":
    asyncio.run(main())
