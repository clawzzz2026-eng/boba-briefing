#!/usr/bin/env python3
"""
Boba Briefing - Daily AI & Tech Digest
Fetches RSS feeds, generates a narrative digest, creates audio via ElevenLabs,
and emails the result to Zach.
"""

import os
import json
import smtplib
import datetime
import feedparser
import requests
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

SECRETS_PATH = Path(__file__).parent.parent / ".secrets"

def load_secrets():
    secrets = {}
    if SECRETS_PATH.exists():
        for line in SECRETS_PATH.read_text().splitlines():
            line = line.strip()
            if line and "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                secrets[k.strip()] = v.strip()
    return secrets

SECRETS = load_secrets()

ELEVENLABS_API_KEY = SECRETS.get("ELEVENLABS_API_KEY")
GMAIL_ADDRESS     = SECRETS.get("GMAIL_ADDRESS")
GMAIL_APP_PASSWORD = SECRETS.get("GMAIL_APP_PASSWORD")
GITHUB_USER       = SECRETS.get("GITHUB_USER")
GITHUB_TOKEN      = SECRETS.get("GITHUB_TOKEN")

# ElevenLabs voice — "Rachel" is natural and clear (free tier)
ELEVENLABS_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"

RSS_FEEDS = [
    ("The Verge",     "https://www.theverge.com/rss/index.xml"),
    ("Ars Technica",  "https://feeds.arstechnica.com/arstechnica/index"),
    ("TechCrunch",    "https://techcrunch.com/feed/"),
]

# Keywords to filter AI/tech relevant stories
AI_KEYWORDS = [
    "ai", "artificial intelligence", "machine learning", "llm", "gpt", "openai",
    "anthropic", "google deepmind", "gemini", "claude", "chatgpt", "robot",
    "automation", "neural", "model", "deep learning", "generative", "agent",
    "tech", "software", "startup", "chip", "gpu", "nvidia", "microsoft", "apple",
    "meta", "amazon", "silicon", "open source"
]

MAX_STORIES = 10  # Max stories to include in digest

# ── RSS Fetching ──────────────────────────────────────────────────────────────

def fetch_feeds():
    stories = []
    for source, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:15]:
                title   = entry.get("title", "")
                summary = entry.get("summary", entry.get("description", ""))
                link    = entry.get("link", "")
                # Filter for relevance
                text = (title + " " + summary).lower()
                if any(kw in text for kw in AI_KEYWORDS):
                    stories.append({
                        "source":  source,
                        "title":   title,
                        "summary": summary[:300],
                        "link":    link,
                    })
        except Exception as e:
            print(f"[warn] Failed to fetch {source}: {e}")
    return stories[:MAX_STORIES]

# ── Digest Generation ─────────────────────────────────────────────────────────

def generate_digest(stories, date_str):
    if not stories:
        return "No relevant stories found today.", ""

    # Build the narrative text
    lines = []
    lines.append(f"# 🧋 Boba Briefing — {date_str}\n")
    lines.append("*Your daily AI & technology digest*\n")
    lines.append("---\n")

    for i, s in enumerate(stories, 1):
        lines.append(f"## {i}. {s['title']}")
        lines.append(f"*{s['source']}*\n")
        lines.append(f"{s['summary']}\n")
        lines.append(f"[Read more]({s['link']})\n")
        lines.append("---\n")

    lines.append("\n*Delivered by Boba Fetch 🧋 — your AI briefing agent*")

    markdown = "\n".join(lines)

    # Plain text version for podcast script (no markdown)
    podcast_lines = [f"Welcome to the Boba Briefing for {date_str}. Here are today's top stories in AI and technology.\n"]
    for i, s in enumerate(stories, 1):
        podcast_lines.append(f"Story {i}: {s['title']}, from {s['source']}. {s['summary']}\n")
    podcast_lines.append("That's your Boba Briefing for today. Stay curious!")

    podcast_script = "\n".join(podcast_lines)
    return markdown, podcast_script

# ── ElevenLabs TTS ────────────────────────────────────────────────────────────

def generate_audio(script, output_path):
    if not ELEVENLABS_API_KEY:
        print("[warn] No ElevenLabs API key, skipping audio.")
        return None
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "text": script[:4500],  # Stay within free tier limits
            "model_id": "eleven_monolingual_v1",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(resp.content)
            print(f"[ok] Audio saved to {output_path}")
            return output_path
        else:
            print(f"[warn] ElevenLabs error {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        print(f"[warn] Audio generation failed: {e}")
        return None

# ── Email ─────────────────────────────────────────────────────────────────────

def send_email(date_str, markdown_body, audio_path=None):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASSWORD:
        print("[warn] Gmail not configured, skipping email.")
        return

    msg = MIMEMultipart("mixed")
    msg["Subject"] = f"🧋 Boba Briefing — {date_str}"
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = GMAIL_ADDRESS

    # HTML body (render markdown as simple HTML)
    html = markdown_body.replace("\n", "<br>").replace("---<br>", "<hr>")
    msg.attach(MIMEText(html, "html"))

    # Attach audio if available
    if audio_path and Path(audio_path).exists():
        with open(audio_path, "rb") as f:
            part = MIMEBase("audio", "mpeg")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="boba-briefing-{date_str}.mp3"')
            msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_ADDRESS, GMAIL_ADDRESS, msg.as_string())
        print(f"[ok] Email sent to {GMAIL_ADDRESS}")
    except Exception as e:
        print(f"[error] Email failed: {e}")

# ── GitHub Push ───────────────────────────────────────────────────────────────

def save_and_push(date_str, markdown, audio_path):
    repo_dir = Path(__file__).parent
    notes_dir = repo_dir / "notes"
    notes_dir.mkdir(exist_ok=True)

    # Save markdown note
    note_path = notes_dir / f"{date_str}.md"
    note_path.write_text(markdown)
    print(f"[ok] Note saved: {note_path}")

    # Git commit and push
    import subprocess
    cmds = [
        ["git", "-C", str(repo_dir), "add", "."],
        ["git", "-C", str(repo_dir), "commit", "-m", f"📰 Boba Briefing {date_str}"],
        ["git", "-C", str(repo_dir), "push"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[warn] Git command failed: {' '.join(cmd)}\n{result.stderr}")
        else:
            print(f"[ok] {' '.join(cmd)}")

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    date_str = datetime.date.today().isoformat()
    print(f"\n🧋 Boba Briefing starting for {date_str}...\n")

    # 1. Fetch stories
    print("[1/4] Fetching RSS feeds...")
    stories = fetch_feeds()
    print(f"      Found {len(stories)} relevant stories")

    # 2. Generate digest
    print("[2/4] Generating digest...")
    markdown, podcast_script = generate_digest(stories, date_str)

    # 3. Generate audio
    print("[3/4] Generating podcast audio...")
    audio_dir = Path(__file__).parent / "audio"
    audio_dir.mkdir(exist_ok=True)
    audio_path = audio_dir / f"{date_str}.mp3"
    generate_audio(podcast_script, str(audio_path))

    # 4. Send email
    print("[4/4] Sending email...")
    send_email(date_str, markdown, str(audio_path) if audio_path.exists() else None)

    # 5. Save and push to GitHub
    print("[5/5] Pushing to GitHub...")
    save_and_push(date_str, markdown, audio_path)

    print("\n✅ Boba Briefing complete!\n")

if __name__ == "__main__":
    main()
