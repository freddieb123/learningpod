#!/usr/bin/env python3
"""
Daily-podcast generator (deep-research edition).

Workflow
1. Ask GPT-4o to invent an interesting long-term-trend topic and return it as a *research prompt*.
2. Feed that prompt back to GPT-4o with a “deep research” role to gather structured notes.
3. Ask GPT-4o to turn those notes into a ~3-minute podcast script.
4. Convert the script to an MP3 with TTS-1-HD.
5. Save the file, prepend a new <item> to feed.xml, and let the GitHub
   Action commit & push.

Requires:
  * openai-python >= 1.25   (for TTS + stream_to_file helper)
  * python-dateutil
  * lxml (only if you prefer—it’s pure ElementTree here)
"""
import os, datetime, xml.etree.ElementTree as ET
from dateutil import tz
from openai import OpenAI

# ---------- config ----------
BASE_URL   = "https://freddieb123.github.io/learningpod"   # <- your Pages domain
VOICE      = "alloy"        # alloy | nova | cascade
MODEL_CHAT = "gpt-4o-mini"  # or gpt-4o / gpt-4o-turbo if you prefer
MODEL_TTS  = "tts-1-hd"
# -----------------------------

# --- repo paths inside the CI runner ---
ROOT   = os.getenv("GITHUB_WORKSPACE", ".")
FEED   = f"{ROOT}/feed.xml"
EP_DIR = f"{ROOT}/episodes"
os.makedirs(EP_DIR, exist_ok=True)

# --- date helpers ---
now_uk     = datetime.datetime.now(tz.gettz("Europe/London"))
yesterday  = (now_uk - datetime.timedelta(days=1)).date()          # for filenames & titles
pub_date   = now_uk.strftime("%a, %d %b %Y %H:%M:%S +0000")        # RFC-2822

# register the iTunes namespace so ElementTree emits <itunes:…> not <ns0:…>
ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")

client = OpenAI()

# --------------------------------------------------------------------
# 1️⃣   Generate a *research prompt* describing an interesting trend
# --------------------------------------------------------------------
prompt_gen_sys = (
    "You are a creative editor for a daily tech-trends podcast. "
    "Invent a single compelling research prompt that asks for deep, data-backed insights "
    "into a long-term trend in technology, product management, or society. "
    "Keep it ≤ 50 words, end with a question mark."
)
prompt_topic = client.chat.completions.create(
    model=MODEL_CHAT,
    messages=[
        {"role": "system", "content": prompt_gen_sys},
        {"role": "user",   "content": "Give me today’s prompt."}
    ]
).choices[0].message.content.strip()

# --------------------------------------------------------------------
# 2️⃣   Perform *deep research* on that topic
#       (Here we just call GPT-4o again; if you have a retrieval-augmented
#        assistant you could swap this block out.)
# --------------------------------------------------------------------
research_sys = (
    "You are a deep-research assistant. Using credible, up-to-date sources, "
    "write detailed notes (~700 words) on the prompt below. "
    "Include 3–5 key data points or citations (title + publication / yyyy) "
    "and a brief ‘why it matters to product leaders’ section."
)
research_notes = client.chat.completions.create(
    model=MODEL_CHAT,
    messages=[
        {"role": "system", "content": research_sys},
        {"role": "user",   "content": prompt_topic}
    ]
).choices[0].message.content.strip()

# --------------------------------------------------------------------
# 3️⃣   Turn the research notes into a ~3-minute podcast script
# --------------------------------------------------------------------
script_sys = (
    "You are a narrative podcast scriptwriter. Using the research notes below, "
    "craft a 3-minute (≈ 700-word) monologue in an engaging radio-host tone. "
    "Open with a hook, explain the trend, weave in the data points conversationally "
    "and close with an upbeat takeaway. Do NOT include the citations verbatim."
)
podcast_script = client.chat.completions.create(
    model=MODEL_CHAT,
    messages=[
        {"role": "system", "content": script_sys},
        {"role": "user",   "content": research_notes}
    ]
).choices[0].message.content.strip()

# --------------------------------------------------------------------
# 4️⃣   TTS → MP3
# --------------------------------------------------------------------
fname = f"{yesterday}.mp3"
path  = f"{EP_DIR}/{fname}"

audio = client.audio.speech.create(
    model=MODEL_TTS,
    input=podcast_script,
    voice=VOICE,
    response_format="mp3"
)
audio.stream_to_file(path)
length_bytes = os.path.getsize(path)

# --------------------------------------------------------------------
# 5️⃣   Update feed.xml (prepend new <item>)
# --------------------------------------------------------------------
tree    = ET.parse(FEED)
channel = tree.getroot().find("channel")

item = ET.Element("item")
ET.SubElement(item, "title").text       = f"{yesterday} — {prompt_topic}"
ET.SubElement(item, "description").text = podcast_script
ET.SubElement(item, "pubDate").text     = pub_date
ET.SubElement(item, "enclosure",
              url=f"{BASE_URL}/episodes/{fname}",
              length=str(length_bytes),
              type="audio/mpeg")
guid = ET.SubElement(item, "guid", isPermaLink="false")
guid.text = f"pod-{yesterday}"

# newest episode first
channel.insert(0, item)
tree.write(FEED, encoding="utf-8", xml_declaration=True)
