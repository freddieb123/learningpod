#!/usr/bin/env python3
import os, datetime, feedparser, xml.etree.ElementTree as ET, requests
from openai import OpenAI
from dateutil import tz

ROOT = os.getenv("GITHUB_WORKSPACE", ".")
FEED = f"{ROOT}/feed.xml"
EP_DIR = f"{ROOT}/episodes"
os.makedirs(EP_DIR, exist_ok=True)

# --- 1. Collect yesterday’s headlines (replace with your own feeds) ---
yesterday = (datetime.datetime.now(tz.UTC) - datetime.timedelta(days=1)).date()
ph = feedparser.parse("https://www.producthunt.com/feed")
headlines = "\n".join(f"{e.title}: {e.link}" for e in ph.entries[:12])

# --- 2. Draft the script with ChatGPT ---
client = OpenAI()
script = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
      {"role": "system", "content": "You are a tech-news radio host."},
      {"role": "user", "content": f"Summarise these items in ≤ 300 words, radio tone:\n{headlines}"}
    ]
).choices[0].message.content

# --- 3. Turn script into MP3 with TTS-1-HD ---
audio = client.audio.speech.create(
    model="tts-1-hd",
    input=script,
    voice="alloy",
    response_format="mp3"
)
fname = f"{yesterday}.mp3"
with open(f"{EP_DIR}/{fname}", "wb") as f:
    f.write(audio.audio)
length_bytes = os.path.getsize(f"{EP_DIR}/{fname}")

# --- 4. Prepend a new <item> to feed.xml ---
tree = ET.parse(FEED)
channel = tree.getroot().find("channel")
item = ET.Element("item")
ET.SubElement(item, "title").text       = f"{yesterday} Product Round-up"
ET.SubElement(item, "description").text = script
ET.SubElement(item, "pubDate").text     = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000")
ET.SubElement(item, "enclosure",
              url=f"https://USERNAME.github.io/my-daily-podcast/episodes/{fname}",
              length=str(length_bytes),
              type="audio/mpeg")
guid = ET.SubElement(item, "guid", isPermaLink="false")
guid.text = f"pod-{yesterday}"
channel.insert(0, item)   # newest first
tree.write(FEED, encoding="utf-8", xml_declaration=True)
