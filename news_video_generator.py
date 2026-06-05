#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║        📰 NEWS VIDEO GENERATOR — Journal Automatique FR              ║
║        Actualités → Script IA → Photos → Audio → Vidéo 9:16         ║
╚══════════════════════════════════════════════════════════════════════╝

Usage:
    python3 news_video_generator.py

Variables d'environnement (.env ou export) :
    ANTHROPIC_KEY  → https://console.anthropic.com  (requis)
    UNSPLASH_KEY   → https://unsplash.com/developers (optionnel, photos HD)
    NEWSAPI_KEY    → https://newsapi.org             (optionnel, backup news)

Sans ANTHROPIC_KEY : demo avec news simulées.
Sans UNSPLASH_KEY  : placeholders visuels stylés.
"""

import os, sys, re, json, time, subprocess, shutil
import requests
import feedparser
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips
import numpy as np

# ─────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────
CONFIG = {
    "ANTHROPIC_KEY": os.getenv("ANTHROPIC_KEY", "VOTRE_CLE_ANTHROPIC"),
    "UNSPLASH_KEY":  os.getenv("UNSPLASH_KEY",  "VOTRE_CLE_UNSPLASH"),
    "NEWSAPI_KEY":   os.getenv("NEWSAPI_KEY",   "VOTRE_CLE_NEWSAPI"),
    "TOP_N":         10,
    "VIDEO_W":       1080,
    "VIDEO_H":       1920,
    "FPS":           24,
    "OUTPUT_DIR":    "./output",
    "ESPEAK_VOICE":  "fr",
    "ESPEAK_SPEED":  155,   # mots/minute
    "ESPEAK_PITCH":  52,
}

W, H = CONFIG["VIDEO_W"], CONFIG["VIDEO_H"]

PALETTE = {
    "bg":      (8,  8,  18),
    "red":     (220, 30, 30),
    "gold":    (255, 185, 0),
    "white":   (255, 255, 255),
    "gray":    (170, 170, 185),
    "dark":    (18,  18,  30),
    "blue":    (30,  80,  200),
}


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 1 — RÉCUPÉRATION DES ACTUALITÉS
# ═══════════════════════════════════════════════════════════════

def fetch_news_via_claude(api_key: str, n: int) -> list[dict]:
    """
    Utilise Claude + web_search pour récupérer les vraies actualités du jour.
    Retourne n news structurées.
    """
    print("  🤖 Claude scrape les actualités en temps réel...")
    today = datetime.now().strftime("%d %B %Y")
    prompt = f"""Tu es un journaliste. Nous sommes le {today}.
Utilise l'outil web_search pour chercher les {n} principales actualités mondiales d'aujourd'hui.
Cherche : "actualités monde aujourd'hui {today}" et "breaking news {today}" et "top news today".

Retourne UNIQUEMENT un JSON valide (sans markdown, sans backticks) :
{{
  "news": [
    {{
      "titre": "Titre court de l'actualité (max 10 mots)",
      "resume": "Résumé factuel en 2-3 phrases (60-80 mots), style journaliste TV",
      "source": "Nom du média source",
      "categorie": "politique|economie|science|technologie|sport|culture|environnement|societe",
      "keywords_photo": ["mot1_anglais", "mot2_anglais", "mot3_anglais"]
    }}
  ],
  "intro": "Introduction du journal en 1 phrase accrocheuse (20 mots max)",
  "outro": "Phrase de clôture dynamique (10 mots max)"
}}

Génère exactement {n} actualités réelles et importantes d'aujourd'hui."""

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": 4000,
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        r = requests.post("https://api.anthropic.com/v1/messages",
                          headers=headers, json=body, timeout=90)
        data = r.json()
        # Extraire le texte JSON de la réponse
        raw_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                raw_text += block["text"]
        # Nettoyer JSON
        raw_text = re.sub(r"```json\s*|\s*```", "", raw_text).strip()
        # Trouver le JSON dans le texte
        match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        if match:
            raw_text = match.group(0)
        result = json.loads(raw_text)
        news_list = result.get("news", [])
        print(f"  ✅ {len(news_list)} actualités récupérées via Claude+WebSearch")
        return result
    except Exception as e:
        print(f"  ⚠️  Erreur Claude API : {e}")
        if 'data' in dir():
            print(f"  Debug: {str(data)[:200]}")
        return None


def fetch_news_rss(n: int) -> list[dict]:
    """Fallback RSS sans API."""
    print("  📡 Scraping RSS feeds...")
    feeds = [
        ("Le Monde",     "https://www.lemonde.fr/rss/une.xml"),
        ("France24",     "https://www.france24.com/fr/rss"),
        ("BBC Monde",    "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Reuters",      "https://feeds.reuters.com/reuters/topNews"),
        ("Al Jazeera",   "https://www.aljazeera.com/xml/rss/all.xml"),
        ("The Guardian", "https://www.theguardian.com/world/rss"),
        ("RFI",          "https://www.rfi.fr/fr/rss-podcasts/rfi-monde"),
        ("DW",           "https://rss.dw.com/rdf/rss-en-all"),
        ("Euronews",     "https://feeds.feedburner.com/euronews/fr/home/"),
        ("Le Figaro",    "https://www.lefigaro.fr/rss/figaro_actualites.xml"),
    ]
    results = []
    seen = set()
    for source, url in feeds:
        if len(results) >= n * 2:
            break
        try:
            f = feedparser.parse(url)
            for entry in f.entries[:3]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                desc = re.sub(r"<[^>]+>", "",
                              entry.get("summary", "") or entry.get("description", "")).strip()
                words = [w for w in title.split() if len(w) > 4][:3]
                results.append({
                    "titre":          title[:80],
                    "resume":         desc[:200] if desc else title,
                    "source":         source,
                    "categorie":      "monde",
                    "keywords_photo": words or ["world", "news", "today"],
                })
        except Exception:
            continue
    print(f"  ✅ {len(results)} articles RSS collectés")
    return results


def get_news(config: dict) -> dict:
    """Récupère les actualités depuis la meilleure source disponible."""
    print("\n🔍 ÉTAPE 1 — Collecte des actualités mondiales...")
    n = config["TOP_N"]

    # Mode 1 : Claude + web_search (meilleur)
    if not config["ANTHROPIC_KEY"].startswith("VOTRE"):
        result = fetch_news_via_claude(config["ANTHROPIC_KEY"], n)
        if result and len(result.get("news", [])) >= 5:
            news = result["news"][:n]
            print(f"\n📋 Top {len(news)} actualités :")
            for i, item in enumerate(news, 1):
                print(f"  {i:2}. [{item['source']}] {item['titre'][:65]}")
            return result

    # Mode 2 : RSS (fallback)
    rss_news = fetch_news_rss(n)
    if rss_news:
        news = rss_news[:n]
        print(f"\n📋 Top {len(news)} actualités (RSS) :")
        for i, item in enumerate(news, 1):
            print(f"  {i:2}. [{item['source']}] {item['titre'][:65]}")
        return {
            "news": news,
            "intro": f"Bonjour, voici les {len(news)} principales actualités de ce {datetime.now().strftime('%A %d %B %Y')}.",
            "outro": "Restez informés. À très bientôt pour de nouvelles actualités.",
        }

    # Mode 3 : Demo statique
    print("  ⚠️  Utilisation des news de démonstration")
    return _demo_news(n)


def _demo_news(n: int) -> dict:
    topics = [
        ("Sommet climatique international", "Les dirigeants mondiaux se réunissent pour discuter des nouvelles mesures contre le changement climatique. Des engagements ambitieux sont attendus.", "ONU", "environnement", ["climate", "summit", "earth"]),
        ("Avancée majeure en intelligence artificielle", "Des chercheurs annoncent une percée dans le domaine de l'IA générale. Cette technologie pourrait transformer de nombreux secteurs.", "MIT Tech", "technologie", ["artificial", "intelligence", "computer"]),
        ("Tensions géopolitiques en Europe de l'Est", "La diplomatie internationale s'intensifie face aux nouvelles tensions dans la région. Des pourparlers sont en cours.", "Reuters", "politique", ["diplomacy", "europe", "politics"]),
        ("Crise économique mondiale : les marchés réagissent", "Les bourses mondiales enregistrent des fluctuations importantes suite aux annonces des banques centrales.", "Bloomberg", "economie", ["stock", "market", "economy"]),
        ("Découverte scientifique sur Mars", "La NASA annonce la découverte de traces d'eau liquide sous la surface martienne, relançant les espoirs de vie extraterrestre.", "NASA", "science", ["mars", "space", "discovery"]),
        ("Record de température mondiale battu", "Les scientifiques confirment que le mois dernier a été le plus chaud jamais enregistré sur Terre.", "Météo France", "environnement", ["temperature", "heat", "weather"]),
        ("Élections dans un pays clé", "Des élections historiques se tiennent avec un taux de participation record. Les résultats pourraient remodeler la politique régionale.", "AFP", "politique", ["election", "vote", "democracy"]),
        ("Pandémie : nouveau variant détecté", "L'OMS surveille un nouveau variant qui se propage rapidement. Les autorités sanitaires appellent à la vigilance.", "OMS", "sante", ["health", "virus", "medicine"]),
        ("Championnat du monde : résultats chocs", "Plusieurs favorites ont été éliminées lors des quarts de finale, créant la surprise dans la compétition internationale.", "L'Équipe", "sport", ["sport", "championship", "competition"]),
        ("Innovation : voiture volante commerciale", "La première voiture volante certifiée pour le grand public entre en production. Prix : 300 000 euros.", "Tech Crunch", "technologie", ["flying", "car", "future"]),
    ]
    news = [{"titre": t[0], "resume": t[1], "source": t[2], "categorie": t[3], "keywords_photo": t[4]} for t in topics[:n]]
    return {
        "news": news,
        "intro": f"Bonjour, bienvenue dans votre journal du {datetime.now().strftime('%d %B %Y')}. Voici les dix actualités qui font le monde.",
        "outro": "Merci de votre fidélité. Restez informés et à très bientôt.",
    }


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 2 — PHOTOS
# ═══════════════════════════════════════════════════════════════

CATEGORY_COLORS = {
    "politique":     [(15,20,60),   (40,60,180)],
    "economie":      [(20,40,15),   (30,120,40)],
    "technologie":   [(5,20,40),    (20,80,160)],
    "science":       [(20,5,50),    (80,20,160)],
    "sport":         [(40,15,5),    (160,60,20)],
    "environnement": [(5,30,15),    (20,100,50)],
    "sante":         [(30,5,20),    (140,20,80)],
    "culture":       [(30,20,5),    (150,90,20)],
    "societe":       [(20,20,20),   (80,80,80)],
    "monde":         [(10,10,30),   (40,40,120)],
}

CATEGORY_ICONS = {
    "politique": "🏛️", "economie": "📈", "technologie": "💻",
    "science": "🔬", "sport": "🏆", "environnement": "🌿",
    "sante": "🏥", "culture": "🎭", "societe": "👥", "monde": "🌍",
}


def download_unsplash_photo(keywords: list[str], api_key: str, path: str) -> bool:
    if api_key.startswith("VOTRE"):
        return False
    try:
        r = requests.get("https://api.unsplash.com/photos/random",
            params={"query": " ".join(keywords), "orientation": "portrait"},
            headers={"Authorization": f"Client-ID {api_key}"},
            timeout=12)
        if r.status_code != 200:
            return False
        img_url = r.json()["urls"]["regular"]
        ir = requests.get(img_url, timeout=25)
        with open(path, "wb") as f:
            f.write(ir.content)
        return True
    except Exception:
        return False


def create_styled_background(keywords: list[str], category: str,
                              number: int, path: str):
    """Crée un fond stylé avec dégradé et éléments graphiques."""
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    colors = CATEGORY_COLORS.get(category, CATEGORY_COLORS["monde"])
    c1, c2 = colors[0], colors[1]

    # Dégradé vertical
    for y in range(H):
        t = y / H
        r = int(c1[0] + t * (c2[0] - c1[0]))
        g = int(c1[1] + t * (c2[1] - c1[1]))
        b = int(c1[2] + t * (c2[2] - c1[2]))
        draw.line([(0,y),(W,y)], fill=(r,g,b))

    # Cercles décoratifs
    import random
    rng = random.Random(number * 42)
    for _ in range(6):
        cx  = rng.randint(0, W)
        cy  = rng.randint(0, H)
        rad = rng.randint(100, 400)
        alpha_r = min(255, c2[0] + 40)
        alpha_g = min(255, c2[1] + 40)
        alpha_b = min(255, c2[2] + 40)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse([cx-rad, cy-rad, cx+rad, cy+rad],
                   fill=(alpha_r, alpha_g, alpha_b, 30))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    # Texte central (icône + numéro)
    try:
        font_num  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 200)
        font_kw   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
    except Exception:
        font_num = font_kw = ImageFont.load_default()

    # Gros numéro semi-transparent au centre
    num_text = str(number)
    draw.text((W//2, H//2), num_text,
              font=font_num, fill=(255,255,255,40), anchor="mm")

    # Mots-clés en bas de zone centrale
    kw_text = "  ·  ".join(k.upper() for k in keywords[:3])
    draw.text((W//2, H//2 + 150), kw_text,
              font=font_kw, fill=(255,255,255,100), anchor="mm")

    img.save(path, "JPEG", quality=92)


def get_photos(script_data: dict, config: dict, photos_dir: Path) -> list[str]:
    print("\n🖼️  ÉTAPE 2 — Récupération des visuels...")
    photos_dir.mkdir(exist_ok=True)
    paths = []
    for i, item in enumerate(script_data["news"]):
        n    = i + 1
        kws  = item.get("keywords_photo", ["news", "world"])
        cat  = item.get("categorie", "monde")
        path = str(photos_dir / f"news_{n:02d}.jpg")

        # Essai Unsplash
        ok = download_unsplash_photo(kws, config["UNSPLASH_KEY"], path)
        if ok:
            print(f"  🖼️  #{n:2} Unsplash OK  [{cat}] {' '.join(kws)}")
        else:
            # Background stylé
            create_styled_background(kws, cat, n, path)
            print(f"  🎨 #{n:2} Fond stylé   [{cat}] {' '.join(kws)}")

        paths.append(path)
        time.sleep(0.2)
    return paths


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 3 — AUDIO (Kokoro TTS — voix naturelle gratuite)
# ═══════════════════════════════════════════════════════════════
# Kokoro : modèle open-source 82M params, Apache 2.0
# Qualité : surpasse Google WaveNet et Amazon Polly
# Install : pip install kokoro soundfile
# Modèle  : ~85MB téléchargé automatiquement au 1er lancement

try:
    from kokoro import KPipeline
    import soundfile as sf
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False

_kokoro_pipeline = None

def _get_kokoro():
    global _kokoro_pipeline
    if _kokoro_pipeline is None:
        print("  🔄 Chargement Kokoro (1ère fois ~3s)...")
        _kokoro_pipeline = KPipeline(lang_code='f', repo_id='hexgrad/Kokoro-82M')
        print("  ✅ Kokoro prêt")
    return _kokoro_pipeline

def text_to_wav(text: str, wav_path: str, config: dict) -> bool:
    """Convertit du texte en WAV — Kokoro en priorité, espeak en fallback."""
    # Essai Kokoro (voix naturelle)
    if KOKORO_AVAILABLE:
        try:
            pipeline = _get_kokoro()
            chunks = []
            for _, _, audio in pipeline(text, voice='ff_siwis', speed=1.08):
                chunks.append(audio)
            if chunks:
                import numpy as np
                sf.write(wav_path, np.concatenate(chunks), 24000)
                return os.path.exists(wav_path)
        except Exception as e:
            print(f"  ⚠️  Kokoro erreur : {e} — fallback espeak")

    # Fallback espeak
    text_clean = re.sub(r'[^\w\s\.,;:!?\-\'\u00C0-\u024F]', ' ', text)
    cmd = ["espeak-ng", "-v", config.get("ESPEAK_VOICE","fr"),
           "-s", str(config.get("ESPEAK_SPEED",155)),
           "-p", str(config.get("ESPEAK_PITCH",52)),
           "-a", "180", "-g", "8", "-w", wav_path, text_clean]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(wav_path)


def wav_to_mp3(wav_path: str, mp3_path: str) -> bool:
    """Convertit WAV en MP3 avec ffmpeg."""
    cmd = ["ffmpeg", "-y", "-i", wav_path,
           "-ar", "44100", "-ab", "128k", mp3_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0 and os.path.exists(mp3_path)


def generate_all_audio(script_data: dict, config: dict, audio_dir: Path) -> list[dict]:
    print("\n🎙️  ÉTAPE 3 — Synthèse vocale (espeak-ng)...")
    audio_dir.mkdir(exist_ok=True)
    segments = []

    def make_audio(text: str, name: str) -> tuple[str | None, float]:
        wav = str(audio_dir / f"{name}.wav")
        mp3 = str(audio_dir / f"{name}.mp3")
        if text_to_wav(text, wav, config):
            if wav_to_mp3(wav, mp3):
                try:
                    clip = AudioFileClip(mp3)
                    dur  = clip.duration
                    clip.close()
                    os.remove(wav)  # cleanup WAV
                    return mp3, dur
                except Exception:
                    pass
        return None, 5.0

    # Intro
    intro_text = script_data.get("intro", "Bonjour, voici les actualités du jour.")
    mp3, dur = make_audio(intro_text, "intro")
    segments.append({"type": "intro", "audio": mp3, "duration": dur,
                      "text": intro_text, "titre": "Journal du Monde"})
    print(f"  ✅ Intro : {dur:.1f}s")

    # News
    for i, item in enumerate(script_data["news"]):
        n    = i + 1
        text = f"Numéro {n}. {item['titre']}. {item['resume']}"
        mp3, dur = make_audio(text, f"news_{n:02d}")
        segments.append({
            "type":     "news",
            "index":    n,
            "audio":    mp3,
            "duration": dur,
            "text":     item["resume"],
            "titre":    item["titre"],
            "source":   item.get("source", ""),
            "categorie":item.get("categorie", "monde"),
            "keywords": item.get("keywords_photo", []),
        })
        print(f"  🎙️  #{n:2} {dur:.1f}s — {item['titre'][:55]}...")

    # Outro
    outro_text = script_data.get("outro", "Merci et à bientôt.")
    mp3, dur = make_audio(outro_text, "outro")
    segments.append({"type": "outro", "audio": mp3, "duration": dur,
                      "text": outro_text, "titre": "Merci"})
    print(f"  ✅ Outro : {dur:.1f}s")

    total = sum(s["duration"] for s in segments)
    print(f"  📊 Durée totale estimée : {total:.0f}s ({total/60:.1f} min)")
    return segments


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 4 — COMPOSITION VIDÉO
# ═══════════════════════════════════════════════════════════════

def _fonts():
    paths = {
        "bold":    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "oblique": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
    }
    f = {}
    for style, p in paths.items():
        try:
            f[f"{style}_xl"]  = ImageFont.truetype(p, 88)
            f[f"{style}_lg"]  = ImageFont.truetype(p, 56)
            f[f"{style}_md"]  = ImageFont.truetype(p, 38)
            f[f"{style}_sm"]  = ImageFont.truetype(p, 28)
            f[f"{style}_xs"]  = ImageFont.truetype(p, 22)
        except Exception:
            d = ImageFont.load_default()
            for s in ["xl","lg","md","sm","xs"]:
                f[f"{style}_{s}"] = d
    return f


def _wrap(text: str, font, max_w: int, draw: ImageDraw) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if draw.textbbox((0,0), test, font=font)[2] <= max_w:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = word
    if cur: lines.append(cur)
    return lines


def _gradient_overlay(img: Image.Image, start_y: int, end_y: int,
                       color: tuple, max_alpha: int = 230) -> Image.Image:
    """Applique un dégradé d'opacité sur une zone."""
    img = img.convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0,0,0,0))
    draw = ImageDraw.Draw(overlay)
    span = end_y - start_y
    for y in range(start_y, min(end_y, H)):
        t = (y - start_y) / span
        alpha = int(max_alpha * (t ** 0.6))
        draw.line([(0,y),(W,y)], fill=(*color[:3], alpha))
    return Image.alpha_composite(img, overlay)


def render_intro(text: str, fonts: dict) -> np.ndarray:
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    # Fond sombre
    for y in range(H):
        t = y/H
        draw.line([(0,y),(W,y)], fill=(int(5+t*20), int(5+t*10), int(15+t*35)))

    img = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Barre rouge haut
    draw.rectangle([0, 0, W, 14], fill=(*PALETTE["red"], 255))

    # Boîte centrale
    bx1, by1, bx2, by2 = 60, H//2-220, W-60, H//2+240
    draw.rounded_rectangle([bx1,by1,bx2,by2], radius=24,
                            fill=(15,15,30,210))
    # Bordure rouge gauche
    draw.rectangle([bx1, by1, bx1+6, by2], fill=(*PALETTE["red"], 255))

    # LOGO TEXT
    draw.text((W//2, H//2-155), "📰", font=fonts["bold_xl"], fill=(*PALETTE["white"], 255), anchor="mm")
    draw.text((W//2, H//2-55), "JOURNAL", font=fonts["bold_lg"], fill=(*PALETTE["white"], 255), anchor="mm")
    draw.text((W//2, H//2+25), "DU MONDE", font=fonts["bold_xl"], fill=(*PALETTE["red"], 255), anchor="mm")

    # Date
    date_str = datetime.now().strftime("%A %d %B %Y").upper()
    draw.text((W//2, H//2+115), date_str, font=fonts["regular_sm"],
              fill=(*PALETTE["gold"], 220), anchor="mm")

    # Intro text
    lines = _wrap(text, fonts["regular_md"], W-140, draw)
    y0 = H//2 + 170
    for line in lines[:3]:
        draw.text((W//2, y0), line, font=fonts["regular_md"],
                  fill=(*PALETTE["gray"], 200), anchor="mm")
        y0 += 46

    draw.rectangle([0, H-14, W, H], fill=(*PALETTE["red"], 255))
    return np.array(img.convert("RGB"))


def render_news_frame(seg: dict, photo_path: str, fonts: dict) -> np.ndarray:
    # Charger photo
    try:
        photo = Image.open(photo_path).convert("RGB")
        pw, ph = photo.size
        ratio = W / H
        if pw/ph > ratio:
            nw = int(ph * ratio)
            photo = photo.crop([(pw-nw)//2, 0, (pw-nw)//2+nw, ph])
        else:
            nh = int(pw / ratio)
            photo = photo.crop([0, (ph-nh)//2, pw, (ph-nh)//2+nh])
        photo = photo.resize((W, H), Image.LANCZOS)
        photo = ImageEnhance.Brightness(photo).enhance(0.45)
        photo = photo.filter(ImageFilter.GaussianBlur(radius=2))
    except Exception:
        photo = Image.new("RGB", (W, H), PALETTE["bg"])

    img = _gradient_overlay(photo, H//3, H, PALETTE["bg"], 240)
    draw = ImageDraw.Draw(img)

    # ── TOP BAR ──
    draw.rectangle([0, 0, W, 12], fill=(*PALETTE["red"], 255))
    now = datetime.now().strftime("%d/%m/%Y  %H:%M")
    draw.text((W//2, 34), now, font=fonts["regular_xs"],
              fill=(*PALETTE["white"], 200), anchor="mm")

    # ── NUMÉRO BADGE ──
    n = seg["index"]
    cx, cy, r = 78, 115, 58
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*PALETTE["red"], 240))
    draw.text((cx, cy), str(n), font=fonts["bold_lg"],
              fill=(*PALETTE["white"], 255), anchor="mm")

    # ── CATÉGORIE TAG ──
    cat     = seg.get("categorie", "monde")
    cat_ico = CATEGORY_ICONS.get(cat, "🌍")
    cat_tag = f"{cat_ico}  {cat.upper()}"
    tag_bbox = draw.textbbox((0,0), cat_tag, font=fonts["regular_sm"])
    tag_w    = tag_bbox[2] - tag_bbox[0] + 24
    draw.rounded_rectangle([W-tag_w-20, 18, W-20, 58],
                            radius=10, fill=(*PALETTE["dark"], 220))
    draw.text((W-tag_w//2-20, 38), cat_tag, font=fonts["regular_sm"],
              fill=(*PALETTE["gold"], 230), anchor="mm")

    # ── ZONE TEXTE BAS ──
    pad = 44
    titre   = seg["titre"]
    body    = seg["text"]
    source  = seg.get("source", "")

    # Titre
    title_lines = _wrap(titre, fonts["bold_lg"], W - pad*2, draw)
    y = H - 380
    for line in title_lines[:3]:
        draw.text((pad, y), line, font=fonts["bold_lg"],
                  fill=(*PALETTE["white"], 255))
        y += 66

    # Séparateur rouge
    draw.rectangle([pad, y+8, pad+90, y+13], fill=(*PALETTE["red"], 255))
    y += 30

    # Body
    body_lines = _wrap(body, fonts["regular_md"], W-pad*2, draw)
    for line in body_lines[:4]:
        draw.text((pad, y), line, font=fonts["regular_md"],
                  fill=(*PALETTE["gray"], 220))
        y += 46

    # Source
    if source:
        draw.text((pad, H-60), f"📡  {source}", font=fonts["regular_sm"],
                  fill=(*PALETTE["gold"], 210))

    # Barre bas
    draw.rectangle([0, H-12, W, H], fill=(*PALETTE["red"], 255))
    return np.array(img.convert("RGB"))


def render_outro(text: str, fonts: dict) -> np.ndarray:
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y/H
        draw.line([(0,y),(W,y)], fill=(int(8+t*25), int(5+t*10), int(18+t*40)))

    img  = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, W, 12], fill=(*PALETTE["red"], 255))
    draw.rectangle([0, H-12, W, H], fill=(*PALETTE["red"], 255))

    draw.rounded_rectangle([80, H//2-200, W-80, H//2+200],
                            radius=24, fill=(15,15,35,200))
    draw.text((W//2, H//2-110), "📰", font=fonts["bold_xl"],
              fill=(*PALETTE["white"],255), anchor="mm")
    draw.text((W//2, H//2-10), "JOURNAL DU MONDE", font=fonts["bold_md"],
              fill=(*PALETTE["white"],255), anchor="mm")

    lines = _wrap(text, fonts["regular_md"], W-140, draw)
    y0 = H//2 + 70
    for line in lines[:2]:
        draw.text((W//2, y0), line, font=fonts["regular_md"],
                  fill=(*PALETTE["gray"],200), anchor="mm")
        y0 += 48

    # Abonnement CTA
    draw.text((W//2, H-140), "👍 LIKE  •  🔔 ABONNE-TOI  •  💬 COMMENTE",
              font=fonts["regular_sm"], fill=(*PALETTE["gold"],200), anchor="mm")

    return np.array(img.convert("RGB"))


def build_video(segments: list[dict], photo_paths: list[str],
                script_data: dict, config: dict, output_dir: Path) -> str:
    print("\n🎬 ÉTAPE 4 — Assemblage et encodage de la vidéo...")
    fonts = _fonts()
    clips = []
    photo_map = {i+1: p for i, p in enumerate(photo_paths)}

    for seg in segments:
        stype = seg["type"]
        dur   = seg.get("duration", 6.0) + 0.4  # + pause

        # Render frame
        if stype == "intro":
            frame = render_intro(seg["text"], fonts)
        elif stype == "outro":
            frame = render_outro(seg["text"], fonts)
        else:
            photo_p = photo_map.get(seg["index"], photo_paths[0] if photo_paths else None)
            frame   = render_news_frame(seg, photo_p, fonts)

        img_clip = ImageClip(frame, duration=dur)

        if seg.get("audio") and os.path.exists(seg["audio"]):
            audio_clip = AudioFileClip(seg["audio"])
            actual_dur = audio_clip.duration + 0.4
            img_clip   = img_clip.with_duration(actual_dur)
            img_clip   = img_clip.with_audio(audio_clip)

        clips.append(img_clip)
        label = seg.get("titre", stype)[:40]
        print(f"  🎞️  [{stype:5}] {label:<42} {img_clip.duration:.1f}s")

    print(f"\n  ⚙️  Encodage MP4 (codec H.264)...")
    final      = concatenate_videoclips(clips, method="compose")
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M")
    out_path   = str(output_dir / f"journal_{timestamp}.mp4")

    final.write_videofile(
        out_path, fps=config["FPS"],
        codec="libx264", audio_codec="aac",
        preset="medium", threads=4, logger=None,
    )
    total_dur = sum(c.duration for c in clips)
    final.close()
    for c in clips:
        try: c.close()
        except: pass

    size_mb = os.path.getsize(out_path) / 1_000_000
    print(f"  ✅ Vidéo encodée : {size_mb:.1f} MB | {total_dur:.0f}s ({total_dur/60:.1f} min)")
    return out_path


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║        📰 NEWS VIDEO GENERATOR — Journal Automatique FR              ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    t0 = time.time()

    output_dir = Path(CONFIG["OUTPUT_DIR"])
    photos_dir = output_dir / "photos"
    audio_dir  = output_dir / "audio"
    for d in [output_dir, photos_dir, audio_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. Actualités
    script_data = get_news(CONFIG)
    if not script_data.get("news"):
        print("❌ Aucune news disponible.")
        sys.exit(1)

    # Sauvegarder le script JSON
    script_path = output_dir / f"script_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 Script : {script_path}")

    # 2. Photos
    photo_paths = get_photos(script_data, CONFIG, photos_dir)

    # 3. Audio
    segments = generate_all_audio(script_data, CONFIG, audio_dir)

    # 4. Vidéo
    video_path = build_video(segments, photo_paths, script_data, CONFIG, output_dir)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  ✅ PIPELINE TERMINÉ en {mins}m{secs:02d}s
║
║  📹 Vidéo  → {video_path}
║  📋 Script → {script_path}
╠══════════════════════════════════════════════════════════════════════╣
║  📈 UPGRADES DISPONIBLES :
║
║  1. Voix premium    → pip install elevenlabs
║                       CONFIG["ELEVENLABS_KEY"] = "votre_clé"
║
║  2. Photos HD       → Clé Unsplash gratuite sur unsplash.com/developers
║                       CONFIG["UNSPLASH_KEY"] = "votre_clé"
║
║  3. News en temps réel → Clé Anthropic sur console.anthropic.com
║                          CONFIG["ANTHROPIC_KEY"] = "votre_clé"
║
║  4. Musique de fond → Déposez music.mp3 dans ./output/
║                       Le script la mixera automatiquement
╚══════════════════════════════════════════════════════════════════════╝
""")
    return video_path


if __name__ == "__main__":
    main()
