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

def clean(text):
    text = unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()[:150]

async def fetch_rss(client, name, url):
    try:
        r = await client.get(url, timeout=15, follow_redirects=True)
        root = ET.fromstring(r.text)
        items = []
        keywords = ["startup","funding","raises","series","launch","million",
                    "billion","saas","marketplace","fintech","acquired","yc",
                    "health","edtech","delivery","app","platform","ai","b2b"]
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
    print("Fetching RSS...")
    async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
        results = await asyncio.gather(*[fetch_rss(client, n, u) for n, u in RSS_FEEDS])
    all_items, seen = [], set()
    for items in results:
        for item in items:
            if item["title"] not in seen:
                seen.add(item["title"])
                all_items.append(item)
    print("Total: " + str(len(all_items)))
    return all_items[:25]

async def analyze(articles):
    print("Analyzing...")
    today = datetime.now().strftime("%d %B %Y")
    news_text = "\n".join("- [" + a["source"] + "] " + a["title"] for a in articles)

    prompt = (
        "You are a startup market analyst. Today is " + today + ".\n\n"
        "Recent tech news (last 48h):\n" + news_text + "\n\n"
        "Find 5 business opportunities for Turkey based on these real news. "
        "Each must be inspired by a real company/trend from the news above. "
        "Turkey context: 85M population, mobile-first, e-commerce growing 30%/yr, "
        "high inflation makes cost-saving SaaS attractive, strong manufacturing base.\n\n"
        "Return ONLY a JSON object, no explanation:\n"
        '{"date":"' + today + '","opportunities":['
        '{"name":"string","emoji":"single emoji","oneLiner":"max 10 words",'
        '"sector":"string","score":85,'
        '"inspired_by":"real company from news",'
        '"real_example":"company - funding or detail",'
        '"tr_status":"Turkey situation 1 sentence",'
        '"tr_idea":"how to apply in Turkey 2 sentences",'
        '"mvp":"first MVP description",'
        '"target":"target customer",'
        '"revenue":"revenue model",'
        '"risks":"main risks 1 sentence",'
        '"why_now":"why now for Turkey 1 sentence"}'
        "]}"
    )

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 1,
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json"
            }
        })

    body = r.json()
    if "error" in body:
        raise ValueError("Gemini error: " + str(body["error"]))

    candidates = body.get("candidates", [])
    if not candidates:
        raise ValueError("No candidates: " + str(body)[:400])

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text","") for p in parts)

    if not text:
        finish = candidates[0].get("finishReason","")
        raise ValueError("Empty text, finishReason=" + finish + " body=" + str(body)[:400])

    text = re.sub(r"```json|```", "", text).strip()
    s, e = text.find("{"), text.rfind("}") + 1
    if s == -1:
        raise ValueError("No JSON: " + text[:300])

    result = json.loads(text[s:e])
    print("Found " + str(len(result.get("opportunities",[]))) + " opportunities")
    return result

COLORS = {
    "fintech": "#3B82F6", "e-ticaret": "#F97316", "marketplace": "#F97316",
    "ecommerce": "#F97316", "food": "#EF4444", "delivery": "#EF4444",
    "saas": "#8B5CF6", "b2b": "#8B5CF6", "health": "#10B981",
    "education": "#F59E0B", "edtech": "#F59E0B", "logistics": "#06B6D4",
    "ai": "#EC4899", "lojistik": "#06B6D4",
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

def build_html(data, history):
    opps = sorted(data.get("opportunities", []), key=lambda x: -x.get("score", 0))
    today = data.get("date", "")
    cards = ""
    for rank, o in enumerate(opps, 1):
        c = clr(o.get("sector", ""))
        cards += (
            '<div class="card" style="border-left:4px solid ' + c + '">'
            '<div class="ch">'
            '<span class="rank" style="background:' + c + '22;color:' + c + '">#' + str(rank) + '</span>'
            '<span class="ce">' + o.get("emoji","") + '</span>'
            '<div style="flex:1">'
            '<div class="cn">' + o.get("name","") + '</div>'
            '<div class="co">' + o.get("oneLiner","") + '</div>'
            '</div>'
            '<span class="badge" style="background:' + c + '20;color:' + c + ';border:1px solid ' + c + '40">' + o.get("sector","") + '</span>'
            '</div>'
            '<div class="sr"><span class="sl">Firsat Skoru</span>' + sbar(o.get("score",0), c) + '</div>'
            '<div class="ins">Kaynak: <em>' + o.get("inspired_by","") + '</em></div>'
            '<details><summary>Tam analizi gor</summary><div class="dg">'
            '<div class="db full"><div class="dl">Gercek Ornek</div>' + o.get("real_example","") + '</div>'
            '<div class="db full"><div class="dl">TR Durumu</div>' + o.get("tr_status","") + '</div>'
            '<div class="db full"><div class="dl">TR Uygulama Fikri</div>' + o.get("tr_idea","") + '</div>'
            '<div class="db"><div class="dl">Ilk MVP</div>' + o.get("mvp","") + '</div>'
            '<div class="db"><div class="dl">Hedef Musteri</div>' + o.get("target","") + '</div>'
            '<div class="db"><div class="dl">Gelir Modeli</div>' + o.get("revenue","") + '</div>'
            '<div class="db"><div class="dl">Neden Simdi</div>' + o.get("why_now","") + '</div>'
            '<div class="db"><div class="dl">Riskler</div>' + o.get("risks","") + '</div>'
            '</div></details></div>'
        )

    hist_html = ""
    for h in reversed(history[-14:]):
        tags = "".join(
            '<span class="htag" style="color:' + clr(o.get("sector","")) + '">' + o.get("emoji","") + " " + o.get("name","") + '</span>'
            for o in h.get("opportunities",[])[:3]
        )
        hist_html += '<div class="hrow"><span class="hd">' + h.get("date","") + '</span><span class="ht">' + tags + '</span></div>'

    avg = round(sum(o.get("score",0) for o in opps) / max(len(opps),1))
    top = opps[0] if opps else {}
    high = len([o for o in opps if o.get("score",0) >= 75])

    return """<!DOCTYPE html><html lang="tr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Scout TR -- """ + today + """</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a12;color:#e0e0f0;font-family:system-ui,sans-serif;padding-bottom:60px}
header{background:#0f0f1e;border-bottom:1px solid #1e1e2e;padding:16px 20px;position:sticky;top:0;z-index:10}
.hi{max-width:900px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
h1{font-family:monospace;font-size:18px;color:#f0f0f8}.sub{font-size:11px;color:#444;margin-top:2px}
.dbadge{background:#1e1e2e;border:1px solid #2a2a3e;border-radius:8px;padding:5px 12px;font-family:monospace;font-size:11px;color:#666}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;background:#10B981;box-shadow:0 0 6px #10B981;margin-right:5px;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
main{max-width:900px;margin:0 auto;padding:16px 20px}
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
.co{font-size:12px;color:#666}
.badge{font-size:10px;font-weight:700;padding:3px 8px;border-radius:99px;flex-shrink:0;white-space:nowrap}
.sr{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-size:11px;color:#444}
.sl{text-transform:uppercase;letter-spacing:.08em}
.ins{font-size:11px;color:#555;margin-bottom:8px;padding:6px 10px;background:#0d0d1a;border-radius:6px;font-style:italic}
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
  <div class="sub">Gercek zamanli -- TechCrunch + HN + Gemini AI</div></div>
  <div class="dbadge">""" + today + """</div>
</div></header>
<main>
  <div class="stats">
    <div class="stat"><div class="sv">""" + str(avg) + """%</div><div class="sl2">Ort. Skor</div></div>
    <div class="stat"><div class="sv">""" + top.get("emoji","") + " " + top.get("name","").split("/")[0][:14] + """</div><div class="sl2">Gunun Firsati</div></div>
    <div class="stat"><div class="sv">""" + str(high) + """</div><div class="sl2">75%+ Skor</div></div>
  </div>
  <div class="src">Son 48 saat: TechCrunch, TheNextWeb, Hacker News -- Gemini 2.5 Flash analizi</div>
  <div class="stitle">Bugünün Firsatlari</div>
  """ + cards + """
  <div class="hist">
    <div class="stitle" style="margin-bottom:12px">Gecmis Taramalar</div>
    """ + (hist_html or '<div style="color:#222;font-size:12px">Henuz gecmis yok.</div>') + """
  </div>
</main>
<footer>Market Scout TR -- Her sabah 09:00 -- Gemini 2.5 Flash -- Ucretsiz</footer>
</body></html>"""

async def send_telegram(data, page_url):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram skipped.")
        return
    opps = sorted(data.get("opportunities",[]), key=lambda x: -x.get("score",0))
    lines = ["Market Scout TR -- " + data.get("date","") + "\n"]
    for i, o in enumerate(opps[:3], 1):
        f = round(o.get("score",0)/10)
        bar = "\u2588"*f + "\u2591"*(10-f)
        lines.append(str(i) + ". " + o.get("emoji","") + " " + o.get("name","") + " -- " + str(o.get("score",0)) + "%")
        lines.append(bar + " | " + o.get("why_now","")[:80])
        lines.append("")
    lines.append("Detaylar: " + page_url)
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.telegram.org/bot" + TELEGRAM_TOKEN + "/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines)},
        )
    print("Telegram: " + ("OK" if r.status_code == 200 else r.text[:80]))

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


# ── İçerik Üretici ────────────────────────────────────────────────────────────

async def generate_content(data):
    """Market Scout raporundan LinkedIn ve TikTok/YouTube içeriği üretir."""
    opps = sorted(data.get("opportunities", []), key=lambda x: -x.get("score", 0))
    today = data.get("date", "")
    top3 = opps[:3]

    opps_text = "\n".join(
        str(i+1) + ". " + o.get("name","") + " (" + str(o.get("score","")) + "%) -- " + o.get("oneLiner","") + " -- Neden simdi: " + o.get("why_now","")
        for i, o in enumerate(top3)
    )

    prompt = (
        "Bugun " + today + ". Asagida Turkiye icin tespit edilmis is firsatlari var:\n\n"
        + opps_text + "\n\n"
        "Bu verileri kullanarak 3 farkli icerik uret. "
        "SADECE JSON dondur, baska hicbir sey yazma:\n\n"
        '{"linkedin":{"hook":"Dikkati ceken ilk cumle (max 2 satir, rakam veya surpriz bir bilgiyle baslayacak)",'
        '"body":"300-400 kelime, profesyonel ton, her firsat icin 2-3 paragraf, LinkedIn formatinda (bosluklu, okunakli)",'
        '"cta":"Harekete gecirici son cumle",'
        '"hashtags":"#GirisimTurkiye #Startup #Teknoloji gibi 5-7 hashtag"},'
        '"tiktok":{"hook":"Ilk 3 saniye sozlu hook (merak uyandirsin)",'
        '"script":"60 saniye TikTok scripti, dogal konusma dili, her cumle ayri satirda",'
        '"captions":"3-5 anahtar kelime caption icin",'
        '"hashtags":"5-7 TikTok hashtag"},'
        '"youtube_shorts":{"hook":"Ilk 5 saniye hook",'
        '"script":"90 saniye YouTube Shorts scripti, biraz daha detayli",'
        '"title":"Video baslik (merak uyandiran, SEO uyumlu)",'
        '"description":"Video aciklamasi (2-3 cumle)"}}'
    )

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=" + GEMINI_API_KEY

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1, "maxOutputTokens": 8192}
        })

    body = r.json()
    if "error" in body:
        print("Content gen error: " + str(body["error"]))
        return None

    candidates = body.get("candidates", [])
    if not candidates:
        return None

    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text","") for p in parts)
    text = re.sub(r"```json|```", "", text).strip()
    s, e = text.find("{"), text.rfind("}") + 1
    if s == -1:
        return None

    return json.loads(text[s:e])


def save_content(content, today, history_content):
    """İçerikleri dosyaya kaydeder ve içerik sayfası HTML'i oluşturur."""
    if not content:
        return

    os.makedirs("docs/content", exist_ok=True)

    date_slug = today.replace(" ", "_")

    # LinkedIn
    li = content.get("linkedin", {})
    def to_str(val):
        if isinstance(val, list): return " ".join(str(v) for v in val)
        return str(val) if val else ""

    linkedin_text = (
        "=== LINKEDIN POST -- " + today + " ===\n\n"
        + to_str(li.get("hook","")) + "\n\n"
        + to_str(li.get("body","")) + "\n\n"
        + to_str(li.get("cta","")) + "\n\n"
        + to_str(li.get("hashtags","")) + "\n"
    )
    with open("docs/content/linkedin_" + date_slug + ".txt", "w", encoding="utf-8") as f:
        f.write(linkedin_text)

    # TikTok
    tt = content.get("tiktok", {})
    tiktok_text = (
        "=== TIKTOK SCRIPT -- " + today + " ===\n\n"
        "HOOK (ilk 3 saniye):\n" + to_str(tt.get("hook","")) + "\n\n"
        "SCRIPT:\n" + to_str(tt.get("script","")) + "\n\n"
        "CAPTIONS: " + to_str(tt.get("captions","")) + "\n"
        "HASHTAGS: " + to_str(tt.get("hashtags","")) + "\n"
    )
    with open("docs/content/tiktok_" + date_slug + ".txt", "w", encoding="utf-8") as f:
        f.write(tiktok_text)

    # YouTube Shorts
    yt = content.get("youtube_shorts", {})
    youtube_text = (
        "=== YOUTUBE SHORTS SCRIPT -- " + today + " ===\n\n"
        "BASLIK: " + to_str(yt.get("title","")) + "\n\n"
        "HOOK (ilk 5 saniye):\n" + to_str(yt.get("hook","")) + "\n\n"
        "SCRIPT:\n" + to_str(yt.get("script","")) + "\n\n"
        "ACIKLAMA:\n" + to_str(yt.get("description","")) + "\n"
    )
    with open("docs/content/youtube_" + date_slug + ".txt", "w", encoding="utf-8") as f:
        f.write(youtube_text)

    # İçerik sayfası HTML
    all_content = [{"date": today, "content": content}] + history_content
    build_content_html(all_content)
    print("Content saved: linkedin, tiktok, youtube for " + today)


def build_content_html(all_content):
    """Tüm içerikleri gösteren HTML sayfası."""
    cards = ""
    for entry in all_content[:14]:
        d = entry.get("date","")
        c = entry.get("content",{})
        li = c.get("linkedin",{})
        tt = c.get("tiktok",{})
        yt = c.get("youtube_shorts",{})
        date_slug = d.replace(" ", "_")

        cards += (
            '<div class="day">'
            '<div class="day-header">' + d + '</div>'
            '<div class="platforms">'

            '<div class="platform">'
            '<div class="plabel linkedin-c">LinkedIn</div>'
            '<div class="phook">' + li.get("hook","")[:120] + '...</div>'
            '<a class="dl-btn" href="content/linkedin_' + date_slug + '.txt" download>Indir</a>'
            '</div>'

            '<div class="platform">'
            '<div class="plabel tiktok-c">TikTok</div>'
            '<div class="phook">' + tt.get("hook","")[:120] + '</div>'
            '<a class="dl-btn" href="content/tiktok_' + date_slug + '.txt" download>Indir</a>'
            '</div>'

            '<div class="platform">'
            '<div class="plabel youtube-c">YouTube Shorts</div>'
            '<div class="phook">' + yt.get("title","")[:120] + '</div>'
            '<a class="dl-btn" href="content/youtube_' + date_slug + '.txt" download>Indir</a>'
            '</div>'

            '</div></div>'
        )

    html = """<!DOCTYPE html><html lang="tr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Market Scout -- Icerik Merkezi</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0a0a12;color:#e0e0f0;font-family:system-ui,sans-serif;padding-bottom:60px}
header{background:#0f0f1e;border-bottom:1px solid #1e1e2e;padding:16px 20px;position:sticky;top:0;z-index:10}
.hi{max-width:900px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
h1{font-family:monospace;font-size:18px;color:#f0f0f8}
.sub{font-size:11px;color:#444;margin-top:2px}
.nav{display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap}
.nav a{font-size:12px;color:#3B82F6;text-decoration:none;padding:6px 14px;border:1px solid #3B82F620;border-radius:8px;background:#3B82F610}
main{max-width:900px;margin:0 auto;padding:16px 20px}
.day{background:#13131f;border:1px solid #1e1e2e;border-radius:12px;padding:16px;margin-bottom:16px}
.day-header{font-family:monospace;font-size:12px;color:#555;margin-bottom:12px;text-transform:uppercase;letter-spacing:.1em}
.platforms{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.platform{background:#0d0d1a;border-radius:8px;padding:12px}
.plabel{font-size:10px;font-weight:700;margin-bottom:6px;text-transform:uppercase;letter-spacing:.08em}
.linkedin-c{color:#0A66C2}.tiktok-c{color:#ff0050}.youtube-c{color:#FF0000}
.phook{font-size:11px;color:#888;line-height:1.5;margin-bottom:10px;min-height:40px}
.dl-btn{display:inline-block;font-size:11px;color:#10B981;border:1px solid #10B98140;border-radius:6px;padding:4px 10px;text-decoration:none;background:#10B98110}
@media(max-width:600px){.platforms{grid-template-columns:1fr}}
</style></head><body>
<header><div class="hi">
  <div><h1>Market Scout -- Icerik Merkezi</h1>
  <div class="sub">Gunluk LinkedIn + TikTok + YouTube Shorts icerik uretimi</div></div>
</div></header>
<main>
  <div class="nav">
    <a href="index.html">Firsat Raporu</a>
    <a href="content.html">Icerik Merkezi</a>
  </div>
  """ + (cards or '<div style="color:#222;font-size:12px">Henuz icerik uretilmedi.</div>') + """
</main>
<footer style="text-align:center;padding:28px;font-size:10px;color:#1e1e2e;font-family:monospace">
Market Scout -- Gunluk Icerik Fabrikasi
</footer>
</body></html>"""

    with open("docs/content.html", "w", encoding="utf-8") as f:
        f.write(html)


# ── main() fonksiyonunu override et ──────────────────────────────────────────
import asyncio as _asyncio

_old_main = main

async def main():
    print("Market Scout TR -- " + datetime.now().strftime("%d.%m.%Y %H:%M"))
    articles = await fetch_all_news()
    data = await analyze(articles)
    today = data.get("date","")

    os.makedirs("docs", exist_ok=True)
    hist_path = "docs/history.json"
    history = json.load(open(hist_path)) if os.path.exists(hist_path) else []
    history = [h for h in history if h.get("date") != today]
    history.append(data)
    history = history[-30:]

    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(build_html(data, history[:-1]))
    with open(hist_path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print("Saved docs/index.html")

    # İçerik üret
    print("Generating content...")
    content = await generate_content(data)

    cont_path = "docs/content_history.json"
    history_content = json.load(open(cont_path)) if os.path.exists(cont_path) else []
    history_content = [h for h in history_content if h.get("date") != today]
    if content:
        history_content.insert(0, {"date": today, "content": content})
    history_content = history_content[:30]
    with open(cont_path, "w", encoding="utf-8") as f:
        json.dump(history_content, f, ensure_ascii=False, indent=2)

    save_content(content, today, history_content[1:])

    u, repo = GITHUB_REPO.split("/")
    await send_telegram(data, "https://" + u + ".github.io/" + repo)
    print("Done!")

if __name__ == "__main__":
    _asyncio.run(main())
