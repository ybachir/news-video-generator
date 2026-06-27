#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║        📰 NEWS VIDEO GENERATOR — Journal Automatique FR              ║
║        Actualités → Résumé IA → Photos → Voix → Vidéo 9:16          ║
╚══════════════════════════════════════════════════════════════════════╝

Pipeline 100% gratuit :
  1. RSS feeds  →  résumé structuré via Groq (Llama 3, gratuit)
  2. Photos     →  Unsplash (gratuit) ou fonds générés localement
  3. Audio      →  edge-tts (Microsoft Neural, gratuit) ou espeak fallback
  4. Vidéo      →  ffmpeg direct (rapide) + template premium sombre/doré

Variables d'environnement (.env ou export) :
    GROQ_API_KEY   → https://console.groq.com  (gratuit, 14 400 req/jour)
    UNSPLASH_KEY   → https://unsplash.com/developers (optionnel, 50 req/h)
"""

import os, sys, re, json, time, subprocess, shutil, asyncio
import requests
import feedparser
from pathlib import Path
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np

# ─────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────
CONFIG = {
    "GROQ_API_KEY":  os.getenv("GROQ_API_KEY",  ""),
    "UNSPLASH_KEY":  os.getenv("UNSPLASH_KEY",   ""),
    "TOP_N":         5,
    "VIDEO_W":       1080,
    "VIDEO_H":       1920,
    "FPS":           30,
    "OUTPUT_DIR":    "./output",
    "MUSIC_VOLUME":  0.07,    # Volume musique de fond (0.0 = off, 0.07 = -23dB sous la voix)
}

W, H = CONFIG["VIDEO_W"], CONFIG["VIDEO_H"]

# ── Template premium : sombre / doré ──────────────────────────
PALETTE = {
    "bg":       (10,  10,  18),    # fond quasi-noir bleuté
    "bg2":      (18,  18,  30),    # fond carte
    "gold":     (245, 197,  24),   # or vif  #F5C518
    "gold2":    (200, 155,  10),   # or foncé
    "white":    (255, 255, 255),
    "gray":     (180, 180, 195),
    "dimgray":  (110, 110, 130),
    "red":      (210,  35,  35),   # pour alertes / breaking
}

CATEGORY_COLORS = {
    "politique":     (30,  45, 110),
    "economie":      (20,  90,  50),
    "technologie":   (20,  60, 130),
    "science":       (70,  20, 140),
    "sport":         (140, 55,  15),
    "environnement": (20, 110,  55),
    "sante":         (130, 20,  75),
    "culture":       (130, 80,  15),
    "societe":       (60,  60,  90),
    "monde":         (35,  35, 100),
}

# Traduction FR -> EN pour le repli Unsplash (les requêtes en anglais
# renvoient nettement plus de résultats que les catégories françaises)
CATEGORY_EN = {
    "politique":     "politics",
    "economie":      "economy business",
    "technologie":   "technology",
    "science":       "science",
    "sport":         "sport stadium",
    "environnement": "nature environment",
    "sante":         "health hospital",
    "culture":       "culture art",
    "societe":       "city people",
    "monde":         "world news",
}

# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 1 — COLLECTE & STRUCTURATION DES NEWS
#  RSS  →  Groq (Llama 3 gratuit)  →  JSON propre
# ═══════════════════════════════════════════════════════════════

RSS_FEEDS = [
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


def fetch_rss_raw(n: int = 20) -> list[dict]:
    """Scrape les RSS feeds et retourne les articles bruts."""
    print("  📡 Scraping RSS feeds...")
    results, seen = [], set()
    for source, url in RSS_FEEDS:
        if len(results) >= n:
            break
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                desc = re.sub(r"<[^>]+>", "",
                              entry.get("summary", "") or
                              entry.get("description", "")).strip()
                results.append({
                    "titre_brut": title[:200],
                    "desc_brute": desc[:400] if desc else title,
                    "source": source,
                })
        except Exception:
            continue
    print(f"  ✅ {len(results)} articles RSS collectés")
    return results[:n]


def structure_with_groq(articles: list[dict], api_key: str, n: int) -> dict | None:
    """
    Envoie les articles bruts à Groq (Llama 3.3, gratuit) pour :
    - sélectionner les n plus importants
    - réécrire en style journaliste TV
    - classer par catégorie
    - extraire les keywords photo
    """
    if not api_key:
        return None

    today = datetime.now().strftime("%d %B %Y")
    articles_txt = "\n".join(
        f"{i+1}. [{a['source']}] {a['titre_brut']} — {a['desc_brute'][:150]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Tu es un journaliste TV professionnel. Nous sommes le {today}.

Voici {len(articles)} articles RSS bruts :
{articles_txt}

Sélectionne les {n} actualités les plus importantes et variées.
Réécris chaque résumé en style journaliste TV (2-3 phrases, 50-70 mots, factuel, dynamique).

Réponds UNIQUEMENT avec ce JSON (sans markdown, sans backticks) :
{{
  "news": [
    {{
      "titre": "Titre court percutant (max 8 mots)",
      "resume": "Résumé journaliste TV 50-70 mots",
      "source": "Nom du média",
      "categorie": "politique|economie|science|technologie|sport|culture|environnement|societe|monde",
      "keywords_photo": ["mot_anglais1", "mot_anglais2", "mot_anglais3"]
    }}
  ],
  "intro": "Accroche d'ouverture dynamique (15 mots max)",
  "outro": "Phrase de clôture (10 mots max)"
}}"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 2000,
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=body, timeout=30
        )
        data = r.json()
        raw = data["choices"][0]["message"]["content"].strip()
        # Nettoyer éventuels backticks
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        # Extraire le JSON
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            print(f"  ✅ {len(result.get('news', []))} news structurées via Groq")
            return result
    except Exception as e:
        print(f"  ⚠️  Groq erreur : {e}")
    return None


def get_news(config: dict) -> dict:
    """Pipeline complet de collecte des news."""
    print("\n🔍 ÉTAPE 1 — Collecte & structuration des actualités...")
    n = config["TOP_N"]

    # 1. Scraper les RSS
    raw_articles = fetch_rss_raw(n * 3)

    # 2. Structurer avec Groq si clé disponible
    if config["GROQ_API_KEY"]:
        print("  🤖 Structuration via Groq (Llama 3.3)...")
        result = structure_with_groq(raw_articles, config["GROQ_API_KEY"], n)
        if result and len(result.get("news", [])) >= 3:
            news = result["news"][:n]
            print(f"\n📋 Top {len(news)} actualités :")
            for i, item in enumerate(news, 1):
                print(f"  {i:2}. [{item['source']}] {item['titre'][:65]}")
            return result

    # 3. Fallback : RSS brut sans IA
    print("  ⚠️  Groq non disponible → RSS brut (qualité réduite)")
    if raw_articles:
        news = []
        for a in raw_articles[:n]:
            words = [w for w in a["titre_brut"].split() if len(w) > 4][:3]
            news.append({
                "titre":          a["titre_brut"][:80],
                "resume":         a["desc_brute"][:200],
                "source":         a["source"],
                "categorie":      "monde",
                "keywords_photo": words or ["world", "news"],
            })
        date_str = datetime.now().strftime("%A %d %B %Y")
        return {
            "news":  news,
            "intro": f"Bonjour, voici les {len(news)} actualités du {date_str}.",
            "outro": "Restez informés. À très bientôt.",
        }

    # 4. Démo statique
    print("  ⚠️  Aucune source disponible → news de démo")
    return _demo_news(n)


def _demo_news(n: int) -> dict:
    topics = [
        ("Sommet climatique international", "Les dirigeants mondiaux se réunissent pour discuter de nouvelles mesures contre le changement climatique. Des engagements ambitieux sont attendus lors de cette session extraordinaire.", "ONU", "environnement", ["climate", "summit", "earth"]),
        ("Percée en intelligence artificielle", "Des chercheurs annoncent une avancée majeure en IA générale. Cette technologie pourrait transformer la médecine, l'éducation et l'industrie dans les prochaines années.", "MIT Tech", "technologie", ["artificial", "intelligence", "robot"]),
        ("Tensions géopolitiques en Europe", "La diplomatie internationale s'intensifie face aux nouvelles tensions régionales. Des pourparlers d'urgence sont en cours entre les principales puissances.", "Reuters", "politique", ["diplomacy", "europe", "politics"]),
        ("Marchés financiers en turbulences", "Les bourses mondiales enregistrent de fortes fluctuations suite aux annonces des banques centrales sur les taux d'intérêt.", "Bloomberg", "economie", ["stock", "market", "finance"]),
        ("Découverte scientifique sur Mars", "La NASA confirme la présence de traces organiques sous la surface martienne, relançant le débat sur la vie extraterrestre.", "NASA", "science", ["mars", "space", "discovery"]),
    ]
    news = [{"titre": t[0], "resume": t[1], "source": t[2], "categorie": t[3], "keywords_photo": t[4]} for t in topics[:n]]
    return {
        "news":  news,
        "intro": f"Bienvenue dans votre journal du {datetime.now().strftime('%d %B %Y')}.",
        "outro": "Merci de votre fidélité. À demain.",
    }


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 2 — PHOTOS
# ═══════════════════════════════════════════════════════════════

def _unsplash_search(query: str, api_key: str, path: str) -> tuple[bool, int, str]:
    """Une tentative de recherche Unsplash. Retourne (succès, status_code, message)."""
    try:
        r = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": query, "orientation": "portrait"},
            headers={"Authorization": f"Client-ID {api_key}"},
            timeout=12
        )
        if r.status_code != 200:
            return False, r.status_code, r.text[:200]
        img_url = r.json()["urls"]["regular"]
        ir = requests.get(img_url, timeout=25)
        if ir.status_code != 200:
            return False, ir.status_code, "échec téléchargement image"
        with open(path, "wb") as f:
            f.write(ir.content)
        return True, 200, "ok"
    except Exception as e:
        return False, 0, f"{type(e).__name__}: {e}"


def download_unsplash_photo(keywords: list[str], api_key: str, path: str,
                             category: str | None = None) -> bool:
    if not api_key:
        print("  ⚠️  Unsplash : UNSPLASH_KEY absente/vide — fond généré utilisé")
        return False

    # Stratégie en cascade : la requête complète est souvent trop spécifique
    # (ex: "senegal iraq world cup football" -> 404 No photos found, car
    # Unsplash traite la query comme un AND de tous les termes). On retombe
    # progressivement sur des requêtes plus génériques qui ont presque
    # toujours des résultats.
    attempts = []
    if keywords:
        attempts.append(" ".join(keywords))          # requête complète
        if len(keywords) > 1:
            attempts.append(keywords[0])              # mot-clé le plus important seul
    if category:
        attempts.append(category)                    # catégorie générale (ex: "sport")
    attempts.append("news")                          # filet de sécurité final

    # Dédupliquer en gardant l'ordre
    seen = set()
    attempts = [a for a in attempts if not (a in seen or seen.add(a))]

    last_status, last_msg = None, None
    for query in attempts:
        ok, status, msg = _unsplash_search(query, api_key, path)
        if ok:
            if query != attempts[0]:
                print(f"  🖼️  Unsplash OK (repli sur '{query}' après échec de la requête initiale)")
            return True
        last_status, last_msg = status, msg

    print(f"  ⚠️  Unsplash HTTP {last_status} — {last_msg} (essais : {attempts})")
    return False


def create_styled_background(keywords: list[str], category: str, number: int, path: str):
    """Fond premium : dégradé sombre + cercles lumineux + numéro discret."""
    import random
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    base  = PALETTE["bg"]
    accent = CATEGORY_COLORS.get(category, CATEGORY_COLORS["monde"])

    # Dégradé vertical bg → accent sombre
    for y in range(H):
        t = (y / H) ** 1.4
        r = int(base[0] + t * (accent[0] - base[0]))
        g = int(base[1] + t * (accent[1] - base[1]))
        b = int(base[2] + t * (accent[2] - base[2]))
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # Halos lumineux
    rng = random.Random(number * 37)
    for _ in range(4):
        cx  = rng.randint(0, W)
        cy  = rng.randint(0, H // 2)
        rad = rng.randint(150, 380)
        overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
                   fill=(*[min(255, c + 50) for c in accent], 25))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    draw = ImageDraw.Draw(img)

    # Numéro discret en filigrane
    try:
        font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 320)
    except Exception:
        font_big = ImageFont.load_default()

    draw.text((W // 2, H // 2 - 80), str(number),
              font=font_big, fill=(*PALETTE["white"], 12), anchor="mm")

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

        ok = download_unsplash_photo(kws, config["UNSPLASH_KEY"], path,
                                      category=CATEGORY_EN.get(cat, "world news"))
        if ok:
            print(f"  🖼️  #{n:2} Unsplash OK  [{cat}]")
        else:
            create_styled_background(kws, cat, n, path)
            print(f"  🎨 #{n:2} Fond premium [{cat}]")

        paths.append(path)
        time.sleep(0.2)
    return paths


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 3 — AUDIO (edge-tts → espeak fallback)
# ═══════════════════════════════════════════════════════════════

EDGE_TTS_VOICE    = "fr-FR-DeniseNeural"
EDGE_TTS_RATE     = "+8%"
EDGE_TTS_RETRIES  = 3
EDGE_TTS_TIMEOUT  = 20   # secondes par tentative


def text_to_wav_edge(text: str, wav_path: str) -> bool:
    """
    Synthèse vocale via edge-tts (Microsoft Neural — gratuit, non officiel).
    Voix    : fr-FR-DeniseNeural
    Retries : 3 tentatives avec backoff exponentiel
    Timeout : 20s par tentative (évite les hangs sur GitHub Actions)
    """
    try:
        import edge_tts
    except ImportError:
        return False

    mp3_tmp = wav_path.replace(".wav", "_edge.mp3")

    async def _fetch():
        communicate = edge_tts.Communicate(
            text, voice=EDGE_TTS_VOICE, rate=EDGE_TTS_RATE
        )
        await communicate.save(mp3_tmp)

    for attempt in range(1, EDGE_TTS_RETRIES + 1):
        try:
            # Timeout via asyncio.wait_for
            asyncio.run(
                asyncio.wait_for(_fetch(), timeout=EDGE_TTS_TIMEOUT)
            )
            if not os.path.exists(mp3_tmp) or os.path.getsize(mp3_tmp) < 1000:
                raise ValueError("Fichier MP3 vide ou absent")

            # MP3 → WAV
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_tmp, wav_path],
                capture_output=True
            )
            try:
                os.remove(mp3_tmp)
            except Exception:
                pass

            if r.returncode == 0 and os.path.exists(wav_path):
                return True
            raise ValueError(f"ffmpeg conversion échouée : {r.stderr[-100:]}")

        except asyncio.TimeoutError:
            print(f"  ⚠️  edge-tts timeout (tentative {attempt}/{EDGE_TTS_RETRIES})")
        except Exception as e:
            print(f"  ⚠️  edge-tts erreur (tentative {attempt}/{EDGE_TTS_RETRIES}) : {e}")

        if attempt < EDGE_TTS_RETRIES:
            time.sleep(2 ** attempt)   # backoff : 2s, 4s

    # Nettoyage si le MP3 temporaire traîne
    try:
        if os.path.exists(mp3_tmp):
            os.remove(mp3_tmp)
    except Exception:
        pass

    return False


def text_to_wav_espeak(text: str, wav_path: str) -> bool:
    """Fallback espeak-ng."""
    text_clean = re.sub(r'[^\w\s\.,;:!?\-\'\u00C0-\u024F]', ' ', text)
    cmd = ["espeak-ng", "-v", "fr", "-s", "155", "-p", "52",
           "-a", "180", "-g", "8", "-w", wav_path, text_clean]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(wav_path)


def wav_to_mp3(wav_path: str, mp3_path: str) -> bool:
    cmd = ["ffmpeg", "-y", "-i", wav_path, "-ar", "44100", "-ab", "128k", mp3_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(mp3_path)


def make_audio(text: str, name: str, audio_dir: Path) -> tuple[str | None, float, str]:
    wav = str(audio_dir / f"{name}.wav")
    mp3 = str(audio_dir / f"{name}.mp3")

    # Essai edge-tts
    ok = text_to_wav_edge(text, wav)
    engine = "edge-tts"

    # Fallback espeak
    if not ok:
        ok = text_to_wav_espeak(text, wav)
        engine = "espeak-ng (fallback)"

    if not ok:
        return None, 5.0, "échec"

    if not wav_to_mp3(wav, mp3):
        return None, 5.0, "échec"

    try:
        os.remove(wav)
    except Exception:
        pass

    try:
        from moviepy import AudioFileClip
        clip = AudioFileClip(mp3)
        dur  = clip.duration
        clip.close()
    except Exception:
        dur = len(text.split()) / 2.5

    return mp3, dur, engine


def generate_all_audio(script_data: dict, config: dict, audio_dir: Path) -> list[dict]:
    print("\n🎙️  ÉTAPE 3 — Synthèse vocale (edge-tts / espeak fallback)...")
    audio_dir.mkdir(exist_ok=True)
    segments = []
    engines_used = []

    # Intro
    intro_text = script_data.get("intro", "Bonjour, voici les actualités du jour.")
    mp3, dur, engine = make_audio(intro_text, "intro", audio_dir)
    engines_used.append(engine)
    segments.append({"type": "intro", "audio": mp3, "duration": dur,
                     "text": intro_text, "titre": "Journal du Monde"})
    print(f"  ✅ Intro : {dur:.1f}s — moteur : {engine}")

    # News
    for i, item in enumerate(script_data["news"]):
        n    = i + 1
        text = f"Numéro {n}. {item['titre']}. {item['resume']}"
        mp3, dur, engine = make_audio(text, f"news_{n:02d}", audio_dir)
        engines_used.append(engine)
        segments.append({
            "type":      "news",
            "index":     n,
            "audio":     mp3,
            "duration":  dur,
            "text":      item["resume"],
            "titre":     item["titre"],
            "source":    item.get("source", ""),
            "categorie": item.get("categorie", "monde"),
            "keywords":  item.get("keywords_photo", []),
        })
        print(f"  🎙️  #{n:2} {dur:.1f}s — moteur : {engine} — {item['titre'][:45]}")

    # Outro
    outro_text = script_data.get("outro", "Merci et à bientôt.")
    mp3, dur, engine = make_audio(outro_text, "outro", audio_dir)
    engines_used.append(engine)
    segments.append({"type": "outro", "audio": mp3, "duration": dur,
                     "text": outro_text, "titre": "Merci"})
    print(f"  ✅ Outro : {dur:.1f}s — moteur : {engine}")

    n_espeak = sum(1 for e in engines_used if "espeak" in e)
    if n_espeak > 0:
        print(f"  ⚠️  ATTENTION : {n_espeak}/{len(engines_used)} segments en fallback espeak-ng "
              f"(voix robotique, pauses marquées) — edge-tts a échoué sur ces segments")

    total = sum(s["duration"] for s in segments)
    print(f"  📊 Durée totale : {total:.0f}s ({total/60:.1f} min)")
    return segments


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 4 — TEMPLATE VIDÉO PREMIUM (sombre / doré)
# ═══════════════════════════════════════════════════════════════

def _fonts():
    paths = {
        "bold":    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    }
    f = {}
    for style, p in paths.items():
        for name, size in [("xl", 96), ("lg", 62), ("md", 40), ("sm", 28), ("xs", 22)]:
            try:
                f[f"{style}_{name}"] = ImageFont.truetype(p, size)
            except Exception:
                f[f"{style}_{name}"] = ImageFont.load_default()
    return f


def _wrap(text: str, font, max_w: int, draw: ImageDraw) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _draw_gold_line(draw: ImageDraw, x1: int, y: int, x2: int, thickness: int = 4):
    """Ligne dorée signature de la template."""
    draw.rectangle([x1, y, x2, y + thickness], fill=PALETTE["gold"])


def _draw_newspaper_icon(draw: ImageDraw, cx: int, cy: int, size: int = 70):
    """
    Icône "journal" dessinée en vectoriel pur (rectangle + lignes de texte stylisées).
    Remplace l'emoji 📰 qui ne s'affiche pas avec DejaVu (glyphe manquant -> carré vide).
    """
    half = size // 2
    x0, y0, x1, y1 = cx - half, cy - half, cx + half, cy + half
    # Feuille de "journal"
    draw.rounded_rectangle([x0, y0, x1, y1], radius=6,
                            outline=(*PALETTE["white"], 255), width=4)
    # Bandeau "titre" en haut, plus épais
    pad = size * 0.16
    draw.rectangle([x0 + pad, y0 + pad, x1 - pad, y0 + pad + size * 0.14],
                    fill=(*PALETTE["gold"], 255))
    # Lignes de texte stylisées
    line_y    = y0 + pad + size * 0.32
    line_h    = size * 0.10
    full_w    = (x1 - pad) - (x0 + pad)
    line_widths = [full_w, full_w, full_w * 0.6]  # dernière ligne plus courte
    for i, w_i in enumerate(line_widths):
        ly = line_y + i * (line_h + size * 0.07)
        draw.rectangle([x0 + pad, ly, x0 + pad + w_i, ly + line_h],
                        fill=(*PALETTE["white"], 220))


def render_intro(text: str, fonts: dict) -> np.ndarray:
    """Écran d'intro : fond sombre, logo centré, bandes dorées."""
    img  = Image.new("RGB", (W, H), PALETTE["bg"])
    draw = ImageDraw.Draw(img)

    # Dégradé subtil
    for y in range(H):
        t = y / H
        r = int(PALETTE["bg"][0] + t * 8)
        g = int(PALETTE["bg"][1] + t * 5)
        b = int(PALETTE["bg"][2] + t * 20)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    img  = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Bandes dorées haut et bas
    draw.rectangle([0, 0,    W, 6],  fill=(*PALETTE["gold"], 255))
    draw.rectangle([0, H-6,  W, H],  fill=(*PALETTE["gold"], 255))

    # Carte centrale
    pad = 70
    cy1, cy2 = H // 2 - 280, H // 2 + 280
    draw.rounded_rectangle([pad, cy1, W - pad, cy2],
                            radius=20, fill=(*PALETTE["bg2"], 230))
    # Bordure gauche dorée
    draw.rectangle([pad, cy1, pad + 5, cy2], fill=(*PALETTE["gold"], 255))

    # Icône "journal" dessinée en vectoriel (évite les glyphes emoji manquants)
    _draw_newspaper_icon(draw, W // 2, H // 2 - 190, size=70)

    # JOURNAL
    draw.text((W // 2, H // 2 - 80), "JOURNAL",
              font=fonts["bold_lg"], fill=(*PALETTE["white"], 255), anchor="mm")

    # DU MONDE en doré
    draw.text((W // 2, H // 2 + 20), "DU MONDE",
              font=fonts["bold_xl"], fill=(*PALETTE["gold"], 255), anchor="mm")

    # Ligne séparatrice
    _draw_gold_line(draw, W // 2 - 80, H // 2 + 95, W // 2 + 80)

    # Date
    date_str = datetime.now().strftime("%A %d %B %Y").upper()
    draw.text((W // 2, H // 2 + 135), date_str,
              font=fonts["regular_sm"], fill=(*PALETTE["gray"], 200), anchor="mm")

    # Texte intro
    lines = _wrap(text, fonts["regular_md"], W - 160, draw)
    y0 = H // 2 + 190
    for line in lines[:3]:
        draw.text((W // 2, y0), line,
                  font=fonts["regular_md"], fill=(*PALETTE["gray"], 190), anchor="mm")
        y0 += 50

    return np.array(img.convert("RGB"))


def render_news_frame(seg: dict, photo_path: str, fonts: dict) -> np.ndarray:
    """Frame news : photo assombrie + overlay premium + texte doré."""
    # ── Photo de fond ──
    try:
        photo = Image.open(photo_path).convert("RGB")
        pw, ph = photo.size
        ratio  = W / H
        if pw / ph > ratio:
            nw = int(ph * ratio)
            photo = photo.crop([(pw - nw) // 2, 0, (pw - nw) // 2 + nw, ph])
        else:
            nh = int(pw / ratio)
            photo = photo.crop([0, (ph - nh) // 2, pw, (ph - nh) // 2 + nh])
        photo = photo.resize((W, H), Image.LANCZOS)
        photo = ImageEnhance.Brightness(photo).enhance(0.30)
        photo = photo.filter(ImageFilter.GaussianBlur(radius=3))
    except Exception:
        photo = Image.new("RGB", (W, H), PALETTE["bg"])

    # ── Overlay dégradé bas ──
    img = photo.convert("RGBA")
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    grad_start = H // 3
    for y in range(grad_start, H):
        t     = (y - grad_start) / (H - grad_start)
        alpha = int(245 * (t ** 0.5))
        od.line([(0, y), (W, y)], fill=(*PALETTE["bg"], alpha))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # ── Barre top ──
    draw.rectangle([0, 0, W, 5], fill=(*PALETTE["gold"], 255))
    now = datetime.now().strftime("%d/%m/%Y  %H:%M")
    draw.text((W // 2, 30), now,
              font=fonts["regular_xs"], fill=(*PALETTE["gray"], 180), anchor="mm")

    # ── Badge numéro (cercle doré) ──
    n  = seg["index"]
    cx, cy, r = 76, 100, 54
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*PALETTE["gold"], 240))
    draw.text((cx, cy), str(n),
              font=fonts["bold_lg"], fill=(*PALETTE["bg"], 255), anchor="mm")

    # ── Tag catégorie (texte seul — pas d'icône emoji, plus fiable visuellement) ──
    cat     = seg.get("categorie", "monde")
    cat_tag = cat.upper()
    bb      = draw.textbbox((0, 0), cat_tag, font=fonts["regular_sm"])
    tag_w   = bb[2] - bb[0] + 28
    tag_x   = W - tag_w - 20
    draw.rounded_rectangle([tag_x, 18, W - 20, 58],
                            radius=8, fill=(*PALETTE["bg2"], 210))
    draw.text((tag_x + tag_w // 2, 38), cat_tag,
              font=fonts["regular_sm"], fill=(*PALETTE["gold"], 230), anchor="mm")

    # ── Zone texte bas ──
    pad  = 44
    y    = H - 420

    # Titre (blanc, gras)
    title_lines = _wrap(seg["titre"], fonts["bold_lg"], W - pad * 2, draw)
    for line in title_lines[:3]:
        draw.text((pad, y), line,
                  font=fonts["bold_lg"], fill=(*PALETTE["white"], 255))
        y += 70

    # Ligne dorée séparatrice
    _draw_gold_line(draw, pad, y + 6, pad + 100)
    y += 28

    # Résumé (gris clair)
    body_lines = _wrap(seg["text"], fonts["regular_md"], W - pad * 2, draw)
    for line in body_lines[:4]:
        draw.text((pad, y), line,
                  font=fonts["regular_md"], fill=(*PALETTE["gray"], 215))
        y += 48

    # Source (doré, bas) — puce ronde vectorielle au lieu d'un emoji
    if seg.get("source"):
        dot_y = H - 65
        draw.ellipse([pad, dot_y - 5, pad + 10, dot_y + 5], fill=(*PALETTE["gold"], 220))
        draw.text((pad + 22, dot_y), seg['source'],
                  font=fonts["regular_sm"], fill=(*PALETTE["gold"], 200), anchor="lm")

    # Barre bas
    draw.rectangle([0, H - 5, W, H], fill=(*PALETTE["gold"], 255))

    return np.array(img.convert("RGB"))


def render_outro(text: str, fonts: dict) -> np.ndarray:
    """Écran outro : CTA abonnement + palette premium."""
    img  = Image.new("RGB", (W, H), PALETTE["bg"])
    draw = ImageDraw.Draw(img)

    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)],
                  fill=(int(10 + t * 10), int(10 + t * 5), int(18 + t * 25)))

    img  = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0,   W, 6],  fill=(*PALETTE["gold"], 255))
    draw.rectangle([0, H-6, W, H],  fill=(*PALETTE["gold"], 255))

    pad = 70
    draw.rounded_rectangle([pad, H // 2 - 260, W - pad, H // 2 + 260],
                            radius=20, fill=(*PALETTE["bg2"], 220))
    draw.rectangle([pad, H // 2 - 260, pad + 5, H // 2 + 260],
                   fill=(*PALETTE["gold"], 255))

    _draw_newspaper_icon(draw, W // 2, H // 2 - 170, size=62)
    draw.text((W // 2, H // 2 - 60), "JOURNAL DU MONDE",
              font=fonts["bold_md"], fill=(*PALETTE["white"], 255), anchor="mm")

    _draw_gold_line(draw, W // 2 - 90, H // 2 - 10, W // 2 + 90)

    lines = _wrap(text, fonts["regular_md"], W - 160, draw)
    y0 = H // 2 + 30
    for line in lines[:2]:
        draw.text((W // 2, y0), line,
                  font=fonts["regular_md"], fill=(*PALETTE["gray"], 200), anchor="mm")
        y0 += 50

    # CTA — texte seul, sans icônes emoji
    draw.text((W // 2, H // 2 + 160),
              "LIKE  •  ABONNE-TOI  •  COMMENTE",
              font=fonts["regular_sm"], fill=(*PALETTE["gold"], 210), anchor="mm")

    return np.array(img.convert("RGB"))


# ═══════════════════════════════════════════════════════════════
#  ÉTAPE 4 — ASSEMBLAGE VIDÉO (ffmpeg direct)
# ═══════════════════════════════════════════════════════════════

def generate_subtitle_filter(text: str, duration: float, W: int, H: int) -> str:
    """
    Génère un filtre ffmpeg drawtext pour sous-titres animés mot par mot.

    Principe :
    - Le texte est découpé en groupes de 3 mots max (plus lisible sur mobile)
    - Chaque groupe apparaît pendant duration/nb_groupes secondes
    - Style : fond semi-transparent noir, texte blanc, bordure noire
    - Position : bas de l'écran (au-dessus de la source)

    Retourne une string filtre ffmpeg prête à injecter dans -vf.
    """
    # Découper en groupes de 3 mots
    words  = text.split()
    groups = []
    for i in range(0, len(words), 3):
        groups.append(" ".join(words[i:i+3]))

    if not groups:
        return ""

    nb       = len(groups)
    # Laisser 0.3s de marge (fade in/out) de chaque côté
    margin   = 0.3
    usable   = max(0.5, duration - 2 * margin)
    per_grp  = usable / nb

    # Position : centré horizontalement, à 200px du bas
    x = "(w-text_w)/2"
    y = f"{H - 220}"

    # Fonte : chercher DejaVu Bold à plusieurs emplacements possibles
    # (les runners GitHub Actions n'ont pas toujours le même chemin)
    import os
    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    font_path = next((p for p in font_candidates if os.path.exists(p)), "")

    # Si aucune police trouvée sur le disque, ne PAS injecter fontfile= du tout
    # (sinon ffmpeg plante sur un chemin invalide et peut faire échouer tout le filtre)
    font_opt = f"fontfile={font_path}:" if font_path else ""

    filters = []
    for idx, grp in enumerate(groups):
        t_start = margin + idx * per_grp
        t_end   = t_start + per_grp

        # Échapper les caractères spéciaux ffmpeg
        grp_escaped = (grp
            .replace("\\", "\\\\")
            .replace("'",  "’")      # apostrophe typographique
            .replace(":",  "\\:")
            .replace(",",  "\\,")
            .replace("[",  "\\[")
            .replace("]",  "\\]")
            .replace("(",  "\\(")
            .replace(")",  "\\)")
        )

        # Fond semi-transparent via box
        f = (
            f"drawtext="
            f"{font_opt}"
            f"text='{grp_escaped}':"
            f"fontsize=42:"
            f"fontcolor=white:"
            f"borderw=2:"
            f"bordercolor=black:"
            f"box=1:"
            f"boxcolor=black@0.55:"
            f"boxborderw=12:"
            f"x={x}:"
            f"y={y}:"
            f"enable='between(t,{t_start:.3f},{t_end:.3f})'"
        )
        filters.append(f)

    return ",".join(filters)


def get_music_path(output_dir: Path) -> str | None:
    """
    Cherche un fichier musique de fond dans cet ordre :
    1. output/music.mp3 (fichier custom posé par l'utilisateur)
    2. assets/ambient_news.mp3 (bundlé dans le repo)
    Retourne None si aucun fichier trouvé.
    """
    candidates = [
        output_dir / "music.mp3",
        Path("assets") / "ambient_news.mp3",
        Path("ambient_news.mp3"),
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 10_000:
            return str(p)
    return None


def mix_background_music(video_path: str, music_path: str,
                          volume: float, output_path: str) -> bool:
    """
    Mixe une musique de fond sous la piste audio de la vidéo.

    - La musique est mise en boucle pour couvrir toute la durée
    - Volume réduit à `volume` (0.07 ≈ -23dB — inaudible mais présente)
    - Fade out 2s en fin de vidéo
    - La piste voix reste intacte et prioritaire
    """
    # Obtenir la durée de la vidéo
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    try:
        total_dur = float(r.stdout.strip())
    except Exception:
        print("  ⚠️  Impossible de lire la durée vidéo — musique ignorée")
        return False

    fadeout_start = max(0, total_dur - 2.0)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", music_path,   # boucle infinie
        "-filter_complex",
        (
            f"[1:a]volume={volume},"               # réduire le volume
            f"afade=t=out:st={fadeout_start:.2f}:d=2.0,"  # fade out final
            f"atrim=duration={total_dur:.2f}[music];"      # couper à la durée exacte
            "[0:a][music]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        ),
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ⚠️  Mix musique échoué : {r.stderr[-200:]}")
        return False
    return True


def validate_mp4(path: str) -> tuple[bool, str]:
    """
    Vérifie qu'un MP4 est lisible et non corrompu via ffprobe.
    Retourne (ok, message).
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=duration,width,height,codec_name",
        "-of", "json", path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"ffprobe erreur : {r.stderr[:200]}"
    try:
        info = json.loads(r.stdout)
        streams = info.get("streams", [])
        if not streams:
            return False, "Aucun stream vidéo détecté"
        s = streams[0]
        w, h   = s.get("width", 0), s.get("height", 0)
        codec  = s.get("codec_name", "?")
        dur    = float(s.get("duration", 0))
        if dur < 5:
            return False, f"Durée trop courte : {dur:.1f}s"
        if w != W or h != H:
            return False, f"Résolution incorrecte : {w}×{h} (attendu {W}×{H})"
        return True, f"{codec} {w}×{h} {dur:.1f}s {os.path.getsize(path)/1e6:.1f}MB"
    except Exception as e:
        return False, f"Erreur parsing ffprobe : {e}"


def cleanup_frames(frames_dir: Path):
    """Supprime le dossier frames temporaire après encodage."""
    try:
        shutil.rmtree(frames_dir)
        print(f"  🧹 Frames supprimées : {frames_dir}")
    except Exception as e:
        print(f"  ⚠️  Nettoyage frames échoué : {e}")


def build_video(segments: list[dict], photo_paths: list[str],
                script_data: dict, config: dict, output_dir: Path) -> str:
    print("\n🎬 ÉTAPE 4 — Assemblage et encodage de la vidéo...")
    fonts      = _fonts()
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    photo_map  = {i + 1: p for i, p in enumerate(photo_paths)}

    # ── Rendre chaque frame en PNG ──
    segment_files = []
    for idx, seg in enumerate(segments):
        stype = seg["type"]
        dur   = seg.get("duration", 6.0) + 0.3

        if stype == "intro":
            frame = render_intro(seg["text"], fonts)
        elif stype == "outro":
            frame = render_outro(seg["text"], fonts)
        else:
            photo_p = photo_map.get(seg["index"], list(photo_map.values())[0])
            frame   = render_news_frame(seg, photo_p, fonts)

        frame_path = str(frames_dir / f"frame_{idx:02d}.png")
        Image.fromarray(frame).save(frame_path)

        segment_files.append({
            "frame":    frame_path,
            "audio":    seg.get("audio"),
            "duration": dur,
            "label":    seg.get("titre", stype)[:40],
        })
        print(f"  🖼️  [{stype:5}] {segment_files[-1]['label']:<42} {dur:.1f}s")

    # ── Encoder chaque segment en clip MP4 ──
    print("\n  ⚙️  Encodage MP4 via ffmpeg...")
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M")
    out_path   = str(output_dir / f"journal_{timestamp}.mp4")
    clip_paths = []

    # Fondu noir : 0.3s en entrée ET sortie de chaque clip
    FADE_D = 0.3

    for i, seg in enumerate(segment_files):
        clip_out = str(frames_dir / f"clip_{i:02d}.mp4")
        dur      = seg["duration"]

        # ── Filtre vidéo : scale + fade + sous-titres animés ──
        sub_filter = ""
        sub_text   = seg.get("text", "") or seg.get("titre", "")
        if sub_text and dur > 1:
            sub_filter = generate_subtitle_filter(sub_text, dur, W, H)

        vf_parts = [
            f"scale={W}:{H}",
            f"fade=t=in:st=0:d={FADE_D}:color=black",
            f"fade=t=out:st={max(0, dur - FADE_D):.2f}:d={FADE_D}:color=black",
        ]
        if sub_filter:
            vf_parts.append(sub_filter)
        vf = ",".join(vf_parts)

        if seg["audio"] and os.path.exists(seg["audio"]):
            # Filtre audio : fade in + fade out (évite les clics)
            af = (
                f"afade=t=in:st=0:d={FADE_D},"
                f"afade=t=out:st={max(0, dur - FADE_D):.2f}:d={FADE_D}"
            )
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", seg["frame"],
                "-i", seg["audio"],
                "-c:v", "libx264", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-b:v", "6M", "-maxrate", "8M", "-bufsize", "12M",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-vf", vf,
                "-af", af,
                "-shortest",
                "-r", str(config["FPS"]),
                clip_out
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", seg["frame"],
                "-t", str(dur),
                "-c:v", "libx264", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-b:v", "6M", "-maxrate", "8M", "-bufsize", "12M",
                "-vf", vf,
                "-r", str(config["FPS"]),
                clip_out
            ]

        r = subprocess.run(cmd, capture_output=True, text=True)
        clip_ok = r.returncode == 0 and os.path.exists(clip_out)

        # Vérifier que le clip a bien une piste vidéo (pas juste audio)
        if clip_ok:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", clip_out],
                capture_output=True, text=True
            )
            if "video" not in probe.stdout:
                clip_ok = False
                print(f"  ⚠️  Clip {i} sans piste vidéo — retry sans sous-titres")
                # Retry sans le filtre sous-titres (cause la plus probable)
                vf_retry = ",".join(vf_parts[:3])  # scale + fades, sans drawtext
                cmd_retry = [a if a != vf else vf_retry for a in cmd]
                r2 = subprocess.run(cmd_retry, capture_output=True, text=True)
                if r2.returncode == 0 and os.path.exists(clip_out):
                    probe2 = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=codec_type", "-of", "csv=p=0", clip_out],
                        capture_output=True, text=True
                    )
                    clip_ok = "video" in probe2.stdout

        if clip_ok:
            clip_paths.append(clip_out)
            print(f"  ✂️   Clip {i:02d} OK  ({dur:.1f}s + fondu {FADE_D}s)")
        else:
            print(f"  ⚠️  Clip {i} échoué : {r.stderr[-150:]}")

    if not clip_paths:
        raise RuntimeError("Aucun clip généré — pipeline interrompu")

    # ── Concaténation finale ──
    # Chemins ABSOLUS dans concat.txt : ffmpeg résout les chemins relatifs
    # par rapport au dossier du fichier concat.txt, pas au cwd — donc on
    # utilise os.path.abspath pour éviter tout problème de double-préfixe.
    concat_file = str(frames_dir / "concat.txt")
    with open(concat_file, "w") as f:
        for cp in clip_paths:
            abs_cp = os.path.abspath(cp)
            f.write(f"file '{abs_cp}'\n")

    cmd_final = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c:v", "libx264", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-b:v", "6M", "-maxrate", "8M", "-bufsize", "12M",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-r", str(config["FPS"]),
        "-movflags", "+faststart",
        out_path
    ]
    r = subprocess.run(cmd_final, capture_output=True, text=True)

    if r.returncode != 0:
        cleanup_frames(frames_dir)
        raise RuntimeError(f"Concaténation ffmpeg échouée : {r.stderr[-300:]}")

    # ── Validation MP4 ──
    ok, msg = validate_mp4(out_path)
    if ok:
        print(f"  ✅ Vidéo validée : {msg}")
    else:
        cleanup_frames(frames_dir)
        raise RuntimeError(f"MP4 corrompu : {msg}")

    # ── Nettoyage frames temporaires ──
    cleanup_frames(frames_dir)

    return out_path


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║        📰 NEWS VIDEO GENERATOR — Pipeline 100% Gratuit              ║
║        RSS → Groq → Photos → edge-tts → ffmpeg → MP4 9:16           ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    t0 = time.time()

    output_dir = Path(CONFIG["OUTPUT_DIR"])
    photos_dir = output_dir / "photos"
    audio_dir  = output_dir / "audio"
    for d in [output_dir, photos_dir, audio_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. News
    script_data = get_news(CONFIG)
    if not script_data.get("news"):
        print("❌ Aucune news disponible.")
        sys.exit(1)

    script_path = output_dir / f"script_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 Script : {script_path}")

    # 2. Photos
    photo_paths = get_photos(script_data, CONFIG, photos_dir)

    # 3. Audio
    segments = generate_all_audio(script_data, CONFIG, audio_dir)

    # 4. Vidéo
    try:
        video_path = build_video(segments, photo_paths, script_data, CONFIG, output_dir)
    except RuntimeError as e:
        print(f"\n❌ PIPELINE ÉCHOUÉ : {e}")
        sys.exit(1)

    # 5. Musique de fond (optionnel)
    music_path = get_music_path(output_dir)
    if music_path and CONFIG["MUSIC_VOLUME"] > 0:
        print(f"\n🎵 ÉTAPE 5 — Mixage musique de fond ({music_path})...")
        mixed_path = video_path.replace(".mp4", "_music.mp4")
        ok = mix_background_music(
            video_path, music_path, CONFIG["MUSIC_VOLUME"], mixed_path
        )
        if ok and os.path.exists(mixed_path):
            os.replace(mixed_path, video_path)   # remplace la vidéo finale
            print("  ✅ Musique mixée")
        else:
            print("  ⚠️  Mix échoué — vidéo sans musique conservée")
    else:
        print("\n🎵 Pas de musique trouvée — dépose assets/ambient_news.mp3 pour l'activer")

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    size_mb = os.path.getsize(video_path) / 1_000_000
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  ✅ PIPELINE TERMINÉ en {mins}m{secs:02d}s
║
║  📹 Vidéo  → {video_path} ({size_mb:.1f} MB)
║  📋 Script → {script_path}
╚══════════════════════════════════════════════════════════════════════╝
""")
    return video_path


if __name__ == "__main__":
    main()
