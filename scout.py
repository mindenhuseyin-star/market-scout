"""
🇹🇷 Market Scout — Gemini ile Gerçek Zamanlı
TechCrunch + TheNextWeb + HN RSS → Gemini analizi → GitHub Pages
Tamamen ücretsiz!
"""
import os, json, asyncio, httpx, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from html import unescape
import re

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "user/market-scout")

# ── RSS Kaynakları ────────────────────────────────────────────────────────────
RSS_FEEDS = [
    ("TechCrunch",         "https://techcrunch.com/feed/"),
    ("TechCrunch Startups","https://techcrunch.com/category/startups/feed/"),
    ("The Next Web",       "https://thenextweb.com/feed/"),
    ("Hacker News",        "https://news.ycombinator.com/rss"),
]

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
                    "health","edtech","delivery","app","platform"]
        for item in root.iter("item"):
            title = clean(item.findtext("title",""))
            desc  = clean(item.findtext("description",""))
            if not title: continue
            if any(k in (title+desc).lower() for k in keywords):
                items.append({"title":title,"desc":desc,"source":name})
        print(f"   ✅ {name}: {len(items)} haber")
        return items
    except Exception as e:
        print(f"   ⚠️ {name}: {e}")
        return []

async def fetch_all_news():
    print("📡 RSS kaynakları taranıyor...")
    async with httpx.AsyncClient(headers={"User-Agent":"Mozilla/5.0"}) as client:
        results = await asyncio.gather(*[fetch_rss(client,n,u) for n,u in RSS_FEEDS])
    all_items, seen = [], set()
    for items in results:
        for item in items:
            if item["title"] not in seen:
                seen.add(item["title"])
                all_items.append(item)
    print(f"   📊 Toplam {len(all_items)} benzersiz haber")
    return all_items[:35]

# ── Gemini Analizi ────────────────────────────────────────────────────────────
async def analyze(articles):
    print("🤖 Gemini analiz yapıyor...")
    today = datetime.now().strftime("%d %B %Y")
    news_text = "\n".join(f"- [{a['source']}] {a['title']} — {a['desc']}" for a in articles)

    prompt = f"""Bugün {today}. Aşağıda son 48 saatin GERÇEK tech/startup haberleri var:

{news_text}

Bu haberleri analiz et. Her fırsat mutlaka yukarıdaki haberlerden birine dayansın.
Türkiye'de henüz olmayan veya çok zayıf olan 6 iş fırsatını belirle.

SADECE şu JSON'u döndür, başka hiçbir şey yazma, markdown kullanma:

{{"date":"{today}","opportunities":[{{"name":"Konsept","emoji":"🚀","oneLiner":"Ne yapar max 10 kelime","sector":"Fintech","score":82,"inspired_by":"Haberdeki gerçek şirket + ne yaptı","real_example":"Şirket — toplanan miktar veya özellik","tr_status":"Türkiye mevcut durum 1 cümle","why_now":"Neden şimdi 2 cümle","market_size":"Tahmini TR pazar büyüklüğü","risks":"Ana risk 1 cümle"}}]}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"

    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 2500}
        })

    body = r.json()
    if "error" in body:
        raise ValueError(f"Gemini hatası: {body['error']}")

    text = body["candidates"][0]["content"]["parts"][0]["text"]
    # JSON çıkar
    text = re.sub(r"```json|```","", text).strip()
    s, e = text.find("{"), text.rfind("}")+1
    if s == -1:
        raise ValueError(f"JSON yok:\n{text[:300]}")
    result = json.loads(text[s:e])
    print(f"   ✅ {len(result.get('opportunities',[]))} fırsat bulundu")
    return result

# ── HTML ──────────────────────────────────────────────────────────────────────
COLORS = {"fintech":"#3B82F6","e-ticaret":"#F97316","marketplace":"#F97316",
          "yemek":"#EF4444","delivery":"#EF4444","saas":"#8B5CF6","b2b":"#8B5CF6",
          "sağlık":"#10B981","health":"#10B981","eğitim":"#F59E0B","education":"#F59E0B"}

def clr(s):
    for k,v in COLORS.items():
        if k in s.lower(): return v
    return "#6366F1"

def sbar(score, html=False):
    c = clr(""); f=round(score/10); b="█"*f+"░"*(10-f)
    if html: return f'<span style="letter-spacing:2px;font-family:monospace">{b}</span> <strong>{score}%</strong>'
    return f"{b} {score}%"

def sbar_c(score, c, html=False):
    f=round(score/10); b="█"*f+"░"*(10-f)
    if html: return f'<span style="color:{c};letter-spacing:2px;font-family:monospace">{b}</span> <strong style="color:{c}">{score}%</strong>'
    return f"{b} {score}%"

def build_html(data, history):
    opps = sorted(data.get("opportunities",[]), key=lambda x:-x.get("score",0))
    today = data.get("date","")
    cards = ""
    for o in opps:
        c = clr(o.get("sector",""))
        cards += f"""<div class="card" style="border-left:4px solid {c}">
  <div class="ch"><span class="ce">{o.get('emoji','🚀')}</span>
    <div style="flex:1"><div class="cn">{o.get('name','')}</div><div class="co">{o.get('oneLiner','')}</div></div>
    <span class="badge" style="background:{c}20;color:{c};border:1px solid {c}40">{o.get('sector','')}</span>
  </div>
  <div class="sr"><span class="sl">TR Uyum Skoru</span>{sbar_c(o.get('score',0),c,True)}</div>
  <div class="ins">🗞️ <em>{o.get('inspired_by','')}</em></div>
  <details><summary>Detayları gör →</summary><div class="dg">
    <div class="db"><div class="dl">📰 Gerçek Örnek</div>{o.get('real_example','')}</div>
    <div class="db"><div class="dl">📊 TR Pazarı</div>{o.get('market_size','')}</div>
    <div class="db"><div class="dl">🇹🇷 TR Durumu</div>{o.get('tr_status','')}</div>
    <div class="db"><div class="dl">⚠️ Risk</div>{o.get('risks','')}</div>
    <div class="db full"><div class="dl">💡 Neden Şimdi?</div>{o.get('why_now','')}</div>
  </div></details>
</div>"""

    hist_html=""
    for h in reversed(history[-14:]):
        tags="".join(f'<span class="htag" style="color:{clr(o.get("sector",""))}">{o.get("emoji","")} {o.get("name","")}</span>' for o in h.get("opportunities",[])[:3])
        hist_html+=f'<div class="hrow"><span class="hd">{h.get("date","")}</span><span class="ht">{tags}</span></div>'

    avg=round(sum(o.get("score",0) for o in opps)/max(len(opps),1))
    top=opps[0] if opps else {}
    high=len([o for o in opps if o.get("score",0)>=75])

    return f"""<!DOCTYPE html><html lang="tr"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>🇹🇷 Market Scout — {today}</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}body{{background:#0a0a12;color:#e0e0f0;font-family:system-ui,sans-serif;padding-bottom:60px}}
header{{background:#0f0f1e;border-bottom:1px solid #1e1e2e;padding:16px 20px;position:sticky;top:0;z-index:10}}
.hi{{max-width:860px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}}
h1{{font-family:monospace;font-size:19px;color:#f0f0f8}}.sub{{font-size:11px;color:#444;margin-top:2px}}
.dbadge{{background:#1e1e2e;border:1px solid #2a2a3e;border-radius:8px;padding:5px 12px;font-family:monospace;font-size:11px;color:#666}}
.dot{{display:inline-block;width:6px;height:6px;border-radius:50%;background:#10B981;box-shadow:0 0 6px #10B981;margin-right:5px;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
main{{max-width:860px;margin:0 auto;padding:16px 20px}}
.stats{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:16px}}
.stat{{background:#13131f;border:1px solid #1e1e2e;border-radius:10px;padding:12px;text-align:center}}
.sv{{font-family:monospace;font-size:17px;font-weight:700;color:#f0f0f8}}.sl2{{font-size:10px;color:#444;margin-top:3px;text-transform:uppercase;letter-spacing:.08em}}
.stitle{{font-family:monospace;font-size:10px;color:#333;text-transform:uppercase;letter-spacing:.12em;margin-bottom:10px}}
.src{{font-size:11px;color:#3B82F6;background:#3B82F610;border:1px solid #3B82F620;border-radius:8px;padding:7px 12px;margin-bottom:14px}}
.card{{background:#13131f;border-radius:12px;padding:14px;margin-bottom:10px;border:1px solid #1e1e2e}}
.ch{{display:flex;align-items:flex-start;gap:10px;margin-bottom:10px}}
.ce{{font-size:24px;line-height:1.3;flex-shrink:0}}.cn{{font-family:monospace;font-size:13px;font-weight:700;margin-bottom:3px}}.co{{font-size:12px;color:#666}}
.badge{{font-size:10px;font-weight:700;padding:3px 8px;border-radius:99px;flex-shrink:0;white-space:nowrap}}
.sr{{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;font-size:11px;color:#444}}
.sl{{text-transform:uppercase;letter-spacing:.08em}}
.ins{{font-size:11px;color:#555;margin-bottom:8px;padding:6px 10px;background:#0d0d1a;border-radius:6px}}
details summary{{font-size:12px;color:#444;cursor:pointer;padding:4px 0;list-style:none}}
details summary::-webkit-details-marker{{display:none}}
details[open] summary{{color:#666;margin-bottom:10px}}
.dg{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.db{{background:#0d0d1a;border-radius:8px;padding:10px 12px;font-size:12px;color:#bbb;line-height:1.5}}
.db.full{{grid-column:1/-1}}.dl{{font-size:10px;color:#555;font-weight:700;margin-bottom:4px;text-transform:uppercase;letter-spacing:.06em}}
.hist{{background:#13131f;border:1px solid #1e1e2e;border-radius:12px;padding:14px;margin-top:18px}}
.hrow{{padding:7px 0;border-bottom:1px solid #1a1a2a;display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
.hrow:last-child{{border:none}}.hd{{font-family:monospace;font-size:10px;color:#333;min-width:80px;flex-shrink:0}}
.ht{{display:flex;gap:8px;flex-wrap:wrap}}.htag{{font-size:11px}}
footer{{text-align:center;padding:28px;font-size:10px;color:#1e1e2e;font-family:monospace}}
@media(max-width:600px){{.dg{{grid-template-columns:1fr}}.db.full{{grid-column:1}}}}
</style></head><body>
<header><div class="hi">
  <div><h1><span class="dot"></span>🇹🇷 Market Scout</h1>
  <div class="sub">Gerçek zamanlı · TechCrunch + HN RSS · Gemini AI</div></div>
  <div class="dbadge">📅 {today}</div>
</div></header>
<main>
  <div class="stats">
    <div class="stat"><div class="sv">{avg}%</div><div class="sl2">Ort. Skor</div></div>
    <div class="stat"><div class="sv">{top.get('emoji','')} {top.get('name','').split('/')[0][:14]}</div><div class="sl2">Günün Fırsatı</div></div>
    <div class="stat"><div class="sv">{high}</div><div class="sl2">Yüksek Pot.</div></div>
  </div>
  <div class="src">📡 Son 48 saat: TechCrunch, TheNextWeb, Hacker News RSS · Gemini 2.0 Flash analizi</div>
  <div class="stitle">📊 Bugünün Fırsatları</div>
  {cards}
  <div class="hist">
    <div class="stitle" style="margin-bottom:12px">📅 Geçmiş Taramalar</div>
    {hist_html or '<div style="color:#222;font-size:12px">Henüz geçmiş yok.</div>'}
  </div>
</main>
<footer>Market Scout · Her sabah 09:00 TR · RSS + Gemini · Tamamen ücretsiz</footer>
</body></html>"""

# ── Telegram (opsiyonel) ──────────────────────────────────────────────────────
async def send_telegram(data, page_url):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ℹ️  Telegram ayarlanmamış, atlandı.")
        return
    opps = sorted(data.get("opportunities",[]), key=lambda x:-x.get("score",0))
    lines = [f"🇹🇷 *Market Scout — {data.get('date','')}*\n📡 _TechCrunch + HN · Gemini_\n\n━━━━━━━━━━━━━━━━━━━━━"]
    for i,o in enumerate(opps[:5],1):
        lines += [f"\n{o.get('emoji','🚀')} *{i}. {o.get('name','')}*",
                  f"_{o.get('oneLiner','')}_",
                  f"`{sbar(o.get('score',0))}`",
                  f"🗞 _{o.get('inspired_by','')[:80]}_",
                  "━━━━━━━━━━━━━━━━━━━━━"]
    lines.append(f"\n🔗 [Tüm detaylar →]({page_url})")
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"text":"\n".join(lines),"parse_mode":"Markdown","disable_web_page_preview":False},
        )
    print("✅ Telegram" if r.status_code==200 else f"⚠️ Telegram: {r.text[:80]}")

# ── Ana akış ──────────────────────────────────────────────────────────────────
async def main():
    print(f"\n🚀 Market Scout — {datetime.now():%d.%m.%Y %H:%M}\n")
    articles = await fetch_all_news()
    data     = await analyze(articles)

    os.makedirs("docs", exist_ok=True)
    hist_path = "docs/history.json"
    history = json.load(open(hist_path)) if os.path.exists(hist_path) else []
    history = [h for h in history if h.get("date") != data.get("date")]
    history.append(data)
    history = history[-30:]

    with open("docs/index.html","w",encoding="utf-8") as f:
        f.write(build_html(data, history[:-1]))
    with open(hist_path,"w",encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print("✅ docs/index.html kaydedildi")

    u, repo = GITHUB_REPO.split("/")
    await send_telegram(data, f"https://{u}.github.io/{repo}")
    print(f"\n🎉 Bitti!\n")

if __name__ == "__main__":
    asyncio.run(main())

name: 🇹🇷 Market Scout

on:
  schedule:
    - cron: "0 6 * * *"  # 09:00 Türkiye (UTC+3)
  workflow_dispatch:

permissions:
  contents: write
  pages: write
  id-token: write

jobs:
  scout:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install httpx
      - name: 🚀 Tara
        env:
          GEMINI_API_KEY:    ${{ secrets.GEMINI_API_KEY }}
          TELEGRAM_TOKEN:    ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID:  ${{ secrets.TELEGRAM_CHAT_ID }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: python scout.py
      - name: 📤 Push
        run: |
          git config user.name "Market Scout"
          git config user.email "bot@scout"
          git add docs/
          git diff --staged --quiet || git commit -m "🇹🇷 $(date +'%d.%m.%Y') taraması"
          git push
      - name: 🌐 GitHub Pages
        uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./docs
          publish_branch: gh-pages
