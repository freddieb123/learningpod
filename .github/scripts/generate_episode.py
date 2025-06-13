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
    "Indigenous philosophies of land stewardship",
    "Philosophy of time amid quantum weirdness",
    "Panpsychism and machine consciousness",
    "Philosophy of humor and internet memes",
    "Pragmatism’s toolbox for policymakers",
    "Existential risk & longtermism",
    "Philosophy of language in multilingual AI",
    "Transhumanism and moral boundaries",
    "Global AI-governance frameworks after the AI-Index",
    "Bias in generative models & fairness metrics",
    "Data privacy in sensor-saturated cities",
    "Deepfake ethics and democratic resilience",
    "CRISPR babies-to-be? Gene-editing frontiers",
    "Climate-justice and loss-and-damage funds",
    "Ethical consumerism vs. corporate greenwash",
    "Autonomous weapons & international law",
    "Corporate “digital responsibility” charters",
    "Space mining and planetary protection",
    "Neuroethics of brain–computer interfaces",
    "Universal Basic Income pilots & dignity",
    "Synthetic-media companions and consent",
    "Geo-engineering moral hazard",
    "Algorithmic transparency mandates",
    "Global birth-rate freefall & economic redesign",
    "Loneliness epidemic and social-connection policy",
    "Four-day work week as productivity strategy",
    "Neurodiversity inclusion in hiring",
    "Regulating the gig economy",
    "Ageing nations & inter-generational contracts",
    "Rural renaissance amid urban depopulation",
    "Climate-driven migration flows",
    "Rise of single-person households",
    "Borderless digital-nomad communities",
    "De-stigmatising mental health at scale",
    "“Polycrisis” narratives in news media",
    "Depolarising politics via deliberative democracy",
    "Hybrid & virtual schooling futures",
    "The future of faith in secular societies",
    "Life after crossing six planetary boundaries",
    "Green-hydrogen price plunge",
    "Microplastics detected in human brains",
    "Marine heatwaves & collapsing fisheries",
    "Rewilding the urban jungle",
    "Circular-economy business blueprints",
    "Biodiversity credits & finance markets",
    "Soil-carbon sequestration tech",
    "Climate tipping-point thresholds",
    "Regenerative textiles & slow fashion",
    "AI for anti-poaching and wildlife counts",
    "Insurance retreat from climate-risk zones",
    "Solar geo-engineering governance debates",
    "Blue-carbon ecosystems (mangroves, seagrass)",
    "Water scarcity & next-gen desalination",
    "Quantum-computing error-correction breakthroughs",
    "Photonic chips & ultra-low-power AI",
    "AI-designed drugs entering clinical trials",
    "Solid-state batteries for e-mobility",
    "AR glasses & spatial-computing interfaces",
    "Blockchain for supply-chain transparency",
    "Synthetic biology for green chemicals",
    "Fusion-energy pilot plants",
    "Edge-AI healthcare wearables",
    "DNA data-storage start-ups",
    "Open-source “agentic” AI models",
    "6G and terahertz wireless",
    "Robots in elder-care",
    "Brain-to-text neuro-decoding",
    "Self-repairing smart materials",
    "Space-based solar-power demos",
    "Carbon-negative concrete",
    "Swarm robotics for disaster response",
    "Hyperloop freight corridors",
    "Personal digital twins in medicine",
    "Afrofuturism & speculative design",
    "Psychedelic-assisted therapy roll-outs",
    "Sports analytics vs. biometric privacy",
    "Esports bids for Olympic status",
    "Gastronomy and cultured-meat dining",
    "Art-NFTs in a post-hype market",
    "Metaverse governance sandboxes",
    "Granting oceans legal personhood",
    "Dark-tourism ethics",
    "Solar-punk urban planning",
    "Cryptoeconomics as inflation hedge",
    "Meme-stock culture after 2021",
    "Citizen-science mega-projects",
    "Algorithmic art criticism",
    "De-extinction and resurrected species",
    "Deep-sea mining controversies",
    "AI for endangered-language revival",
    "Space-debris removal business models",
    "Holistic-health apps & data monetisation",
    "Digital legacy and post-mortem avatars",
]

USED_PATH = f"{ROOT}/.used_topics.json"      # hidden file committed to the repo
# ----------------------------------


# --- repo paths inside the CI runner ---
ROOT   = os.getenv("GITHUB_WORKSPACE", ".")
FEED   = f"{ROOT}/feed.xml"
EP_DIR = f"{ROOT}/episodes"
os.makedirs(EP_DIR, exist_ok=True)

USED_PATH = f"{ROOT}/.used_topics.json"  

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
