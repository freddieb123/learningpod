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

# ---------- topic bank ----------
TOPICS = [
    "Nietzsche’s “God is dead” and secular ethics in 2025",
    "The Will-to-Power vs. personal-branding culture",
    "Stoicism as an antidote to climate anxiety",
    "Camus’ Absurdism in the post-truth era",
    "Confucian revival in AI-shaped East Asia",
    "Buddhist non-self and digital avatars",
    "Feminist epistemology & algorithmic bias",
    # … keep the list exactly as you pasted it …
    "Digital legacy and post-mortem avatars",
]
USED_PATH = f"{ROOT}/.used_topics.json"      # hidden file committed to the repo
# ----------------------------------


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

import random, json, itertools

# --------------------------------------------------------------------
# 1️⃣   Pick a fresh topic (random, no repeats)
# --------------------------------------------------------------------
try:
    with open(USED_PATH) as fh:
        used = set(json.load(fh))
except (FileNotFoundError, json.JSONDecodeError):
    used = set()

available = [i for i in range(len(TOPICS)) if i not in used]
if not available:
    raise SystemExit("🎉  All 100 topics are done. Add more before tomorrow’s run!")

idx           = random.choice(available)
prompt_topic  = TOPICS[idx]                     # this replaces the GPT-invented prompt
used.add(idx)                                  # persist the choice

with open(USED_PATH, "w") as fh:
    json.dump(sorted(used), fh, indent=2)


# --------------------------------------------------------------------
# 2️⃣   Perform *deep research* on that topic
#       (Here we just call GPT-4o again; if you have a retrieval-augmented
#        assistant you could swap this block out.)
# --------------------------------------------------------------------
research_sys = (
    "You are a deep-research assistant. Using credible, up-to-date sources, "
    "write detailed notes (~2000 words) on the topic below. "
    "Include 3–5 key data points or citations (title + publication / yyyy). And make sure it's relevant to day to day life today. It should be a briefing that helps foundational understanding to prepare the listener for a debate they're about to have in that area."
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
script = client.chat.completions.create(
    model=MODEL_CHAT,
    messages=[
        {
            "role": "system",
            "content": (
                "You are a narrative podcast writer. Turn the research notes into a "
                "10-minute (~2000-word) monologue. Keep it engaging and conversational. "
                "Do NOT include the raw citations."
            ),
        },
        {"role": "user", "content": research_notes},
    ],
).choices[0].message.content.strip()

# --------------------------------------------------------------------
# 4️⃣   TTS → MP3
# --------------------------------------------------------------------
from pydub import AudioSegment

VOICE = "alloy"
MAX_LEN = 4000  # safety buffer below the 4096-char limit

# --- Split script ---
def split_text(text, maxlen=MAX_LEN):
    paras = text.split("\n\n")
    chunks, current = [], ""
    for para in paras:
        if len(current) + len(para) < maxlen:
            current += para + "\n\n"
        else:
            chunks.append(current.strip())
            current = para + "\n\n"
    if current: chunks.append(current.strip())
    return chunks

parts = split_text(script)

# --- Generate audio chunks ---
full_audio = AudioSegment.silent(0)

for i, part in enumerate(parts):
    audio = client.audio.speech.create(
        model="tts-1-hd",
        input=part,
        voice=VOICE,
        response_format="mp3"
    )
    temp_file = f"/tmp/chunk_{i}.mp3"
    audio.stream_to_file(temp_file)
    full_audio += AudioSegment.from_file(temp_file) + AudioSegment.silent(200)

# --- Save final mp3 ---
fname = f"{yesterday}.mp3"
path  = f"{EP_DIR}/{fname}"
full_audio.export(path, format="mp3")
length_bytes = os.path.getsize(path)


# --------------------------------------------------------------------
# 5️⃣   Update feed.xml (prepend new <item>)
# --------------------------------------------------------------------
tree    = ET.parse(FEED)
channel = tree.getroot().find("channel")

item = ET.Element("item")
ET.SubElement(item, "title").text       = f"{yesterday} — {prompt_topic}"
ET.SubElement(item, "description").text = script
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
