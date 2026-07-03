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


# ═══════════════════════════════════════════════════════════════════
#  NOUVEAU FILTRAGE EN 3 ÉTAGES (l'ancien /photos/random prenait une
#  photo AU HASARD parmi les matchs vagues — d'où les images hors-sujet)
#
#  1. /search/photos → 10 candidats portrait avec descriptions + tags
#  2. Scoring lexical : recouvrement entre la requête/les mots-clés et
#     les métadonnées de chaque photo → classement par pertinence
#  3. Validation VISION : Groq Llama 4 Scout (gratuit) regarde les 3
#     meilleurs candidats et répond si la photo illustre VRAIMENT le
#     titre — premier OUI retenu. Un fond neutre vaut toujours mieux
#     qu'une photo à contresens.
# ═══════════════════════════════════════════════════════════════════

VISION_MODELS = [
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.2-11b-vision-preview",
]
_working_vision_model = [None]   # cache du modèle qui répond


def _search_candidates(query: str, api_key: str, per_page: int = 10) -> list[dict]:
    """Recherche Unsplash et retourne les candidats avec leurs métadonnées."""
    try:
        r = requests.get(
            "https://api.unsplash.com/search/photos",
            params={"query": query, "orientation": "portrait",
                    "content_filter": "high", "per_page": per_page},
            headers={"Authorization": f"Client-ID {api_key}"},
            timeout=12
        )
        if r.status_code != 200:
            return []
        return r.json().get("results", [])
    except Exception:
        return []


def _score_candidate(photo: dict, wanted_tokens: set[str]) -> float:
    """Score lexical : recouvrement entre les tokens recherchés et les
    métadonnées de la photo (description, alt, tags Unsplash)."""
    text = " ".join([
        photo.get("alt_description") or "",
        photo.get("description") or "",
        " ".join(t.get("title", "") for t in (photo.get("tags") or [])),
    ]).lower()
    if not text.strip() or not wanted_tokens:
        return 0.0
    found = sum(1 for tok in wanted_tokens if tok in text)
    return found / len(wanted_tokens)


def _vision_validates(photo: dict, titre: str, groq_key: str) -> bool | None:
    """Demande à un modèle vision Groq si la photo illustre le titre.
    Retourne True/False, ou None si la vision est indisponible (on se
    rabat alors sur le seul score lexical)."""
    if not groq_key:
        return None
    thumb = (photo.get("urls") or {}).get("small")
    if not thumb:
        return None
    models = ([_working_vision_model[0]] if _working_vision_model[0]
              else VISION_MODELS)
    for model in models:
        try:
            r = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {groq_key}",
                         "Content-Type": "application/json"},
                json={
                    "model": model, "max_tokens": 5, "temperature": 0,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": thumb}},
                            {"type": "text", "text":
                             f"Sujet d'actualité : \"{titre}\". "
                             "Cette photo peut-elle illustrer ce sujet dans un "
                             "journal vidéo SANS contresens ni hors-sujet ? "
                             "Réponds uniquement OUI ou NON."},
                        ],
                    }],
                },
                timeout=20,
            )
            if r.status_code != 200:
                continue
            _working_vision_model[0] = model
            answer = r.json()["choices"][0]["message"]["content"].strip().upper()
            return answer.startswith("OUI") or answer.startswith("YES")
        except Exception:
            continue
    return None


def _download(photo: dict, path: str) -> bool:
    try:
        ir = requests.get(photo["urls"]["regular"], timeout=25)
        if ir.status_code != 200:
            return False
        with open(path, "wb") as f:
            f.write(ir.content)
        return True
    except Exception:
        return False


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


def find_best_photo(item: dict, api_key: str, groq_key: str, path: str,
                    category: str | None = None,
                    used_ids: set | None = None) -> bool:
    """Sélection intelligente : requête de scène → scoring → vision.

    Cascade de requêtes : photo_query (scène précise) → mots-clés →
    catégorie. À chaque étage, les candidats sont classés par score
    lexical ; les 3 meilleurs passent la validation vision Groq.
    `used_ids` évite de réutiliser la même photo sur deux sujets."""
    if not api_key:
        print("  ⚠️  Unsplash : UNSPLASH_KEY absente/vide — fond généré utilisé")
        return False

    used_ids = used_ids if used_ids is not None else set()
    keywords = _filter_sensitive_keywords(item.get("keywords_photo", []))
    titre    = item.get("titre", "")

    queries = []
    pq = (item.get("photo_query") or "").strip()
    if pq and not (set(pq.lower().split()) & SENSITIVE_TERMS):
        queries.append(pq)
    if keywords:
        queries.append(" ".join(keywords[:2]))
        queries.append(keywords[0])
    if category:
        queries.append(category)
    seen = set()
    queries = [q for q in queries if q and not (q in seen or seen.add(q))]

    for qi, query in enumerate(queries):
        candidates = _search_candidates(query, api_key)
        candidates = [c for c in candidates if c.get("id") not in used_ids]
        if not candidates:
            continue

        wanted = {t for t in (query.lower().split() +
                              [k.lower() for k in keywords]) if len(t) > 2}
        candidates.sort(key=lambda c: _score_candidate(c, wanted), reverse=True)

        # Validation vision sur les 3 meilleurs (requête principale et
        # mots-clés seulement — pas sur le filet catégorie, déjà générique)
        use_vision = qi < len(queries) - (1 if category else 0)
        for cand in candidates[:3]:
            verdict = _vision_validates(cand, titre, groq_key) if use_vision else None
            if verdict is False:
                continue            # la vision rejette → candidat suivant
            if _download(cand, path):
                used_ids.add(cand.get("id"))
                tag = "vision ✓" if verdict else "score lexical"
                alt = (cand.get("alt_description") or "?")[:55]
                print(f"  🖼️  ['{query}' → {tag}] {alt}")
                return True

    print(f"  ⚠️  Aucun candidat pertinent (essais : {queries})")
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
    used_ids: set = set()     # anti-doublons : jamais 2x la même photo
    for i, item in enumerate(script_data["news"]):
        n    = i + 1
        kws  = item.get("keywords_photo", ["news", "world"])
        cat  = item.get("categorie", "monde")
        path = str(photos_dir / f"news_{n:02d}.jpg")

        ok = find_best_photo(item, config["UNSPLASH_KEY"],
                             config.get("GROQ_API_KEY", ""), path,
                             category=CATEGORY_EN.get(cat, "world news"),
                             used_ids=used_ids)
        if ok:
            print(f"  🖼️  #{n:2} Unsplash OK  [{cat}]")
        else:
            create_styled_background(kws, cat, n, path)
            print(f"  🎨 #{n:2} Fond premium [{cat}]")

        paths.append(path)
        time.sleep(0.2)
    return paths
