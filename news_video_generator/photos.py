"""
photos.py — ÉTAPE 2 : Récupération des visuels.

Unsplash (avec cascade de secours et filtrage de mots-clés sensibles) ou,
en repli, un fond stylisé généré localement.
"""
import time
import random
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from .config import W, H, PALETTE, CATEGORY_COLORS, CATEGORY_EN


def _unsplash_search(query: str, api_key: str, path: str) -> tuple[bool, int, str]:
    """Une tentative de recherche Unsplash. Retourne (succès, status_code, message)."""
    try:
        r = requests.get(
            "https://api.unsplash.com/photos/random",
            params={"query": query, "orientation": "portrait", "content_filter": "high"},
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


# Termes à exclure des mots-clés avant recherche Unsplash : même générés
# par Groq pour un sujet neutre (ex: "paix", "accord"), certains mots-clés
# adjacents renvoient des photos de conflit/violence/manifestation sur
# Unsplash (banque d'images généraliste, pas de tri éditorial). On préfère
# rater une photo pertinente plutôt que risquer une image choquante ou
# hors-sujet sur un registre sensible.
SENSITIVE_TERMS = {
    "war", "conflict", "soldier", "soldiers", "military", "army", "weapon",
    "gun", "protest", "protester", "protesters", "riot", "violence",
    "attack", "bomb", "terrorism", "refugee", "crisis", "death", "dead",
    "victim", "victims", "blood", "fight", "battle", "demonstration",
}


def _filter_sensitive_keywords(keywords: list[str]) -> list[str]:
    """Retire les mots-clés correspondant à des termes sensibles."""
    return [k for k in keywords if k.lower().strip() not in SENSITIVE_TERMS]


def download_unsplash_photo(keywords: list[str], api_key: str, path: str,
                             category: str | None = None) -> bool:
    if not api_key:
        print("  ⚠️  Unsplash : UNSPLASH_KEY absente/vide — fond généré utilisé")
        return False

    keywords = _filter_sensitive_keywords(keywords)

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
    img  = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)

    base   = PALETTE["bg"]
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
