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
