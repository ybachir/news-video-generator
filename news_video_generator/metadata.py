"""
metadata.py — ÉTAPE 6 : Métadonnées de publication.

Construit et sauvegarde un metadata.json à côté du MP4 final, consommé
automatiquement par publish.py pour générer un titre YouTube, une
description et une caption Instagram RICHES (avec les vrais titres du
jour) au lieu de textes génériques identiques chaque jour.
"""
import json
from pathlib import Path
from datetime import datetime

from .config import date_fr

DEFAULT_HASHTAGS = ["actualités", "journal", "news", "monde", "information"]

# Hashtags fixes ajoutés à CHAQUE vidéo, quel que soit le thème/l'édition :
# - "Shorts" aide YouTube à classer explicitement le contenu dans le flux
#   Shorts (améliore la découverte au-delà du simple format 9:16).
# - Le hashtag de marque est IDENTIQUE sur toutes les vidéos (journal,
#   worldcup, france, deepdive) — la chaîne reste la même, ça permet à un
#   spectateur qui a aimé une vidéo de retrouver toutes les autres en un
#   clic, et construit une identité reconnaissable dans le temps.
BRAND_HASHTAG = "lessentieldelactu"
ALWAYS_ON_HASHTAGS = ["Shorts", BRAND_HASHTAG]

# Plafond total (spécifiques + fixes) — au-delà, Instagram/TikTok
# pénalisent légèrement (perçu comme spam) et YouTube n'exploite quasi
# rien au-delà des hashtags affichés au-dessus du titre.
MAX_HASHTAGS = 10


def build_metadata(script_data: dict, video_path: str) -> dict:
    """Assemble les métadonnées de publication à partir du script du jour."""
    date_str = date_fr(datetime.now(), with_weekday=False)
    titres   = [item.get("titre", "") for item in script_data.get("news", [])]

    hashtags = script_data.get("hashtags") or DEFAULT_HASHTAGS
    hashtags = [h.lstrip("#").strip() for h in hashtags if h.strip()]

    # Les hashtags fixes priment : s'ils ne sont pas déjà présents (comparaison
    # insensible à la casse), on réserve leur place plutôt que de risquer de
    # les perdre en coupant à MAX_HASHTAGS après les avoir ajoutés en fin de liste.
    seen_lower    = {h.lower() for h in hashtags}
    missing_fixed = [t for t in ALWAYS_ON_HASHTAGS if t.lower() not in seen_lower]
    room          = max(0, MAX_HASHTAGS - len(missing_fixed))
    hashtags      = hashtags[:room] + missing_fixed

    titre_video = (script_data.get("titre_video")
                   or f"Les actus du jour — {date_str}")[:95]

    # Description YouTube : sommaire réel du jour → meilleur SEO,
    # description unique chaque jour (YouTube pénalise le contenu dupliqué)
    lignes_sommaire = "\n".join(f"  {i}. {t}" for i, t in enumerate(titres, 1))
    description = (
        f"📰 L'essentiel de l'actu — {date_str}\n\n"
        f"Au sommaire aujourd'hui :\n{lignes_sommaire}\n\n"
        f"L'essentiel de l'actualité mondiale en 3 minutes, tous les jours.\n\n"
        + " ".join(f"#{h.replace(' ', '')}" for h in hashtags)
    )

    # Caption Instagram : plus courte, hashtags en fin
    caption = (
        f"📰 L'essentiel de l'actu — {date_str}\n\n"
        + "\n".join(f"▪️ {t}" for t in titres[:5])
        + "\n\n⏱️ L'essentiel en 3 minutes\n\n"
        + " ".join(f"#{h.replace(' ', '')}" for h in hashtags)
    )[:2200]   # limite Meta

    return {
        "date":        datetime.now().strftime("%Y-%m-%d"),
        "video_file":  Path(video_path).name,
        "titre_video": titre_video,
        "description": description,
        "caption":     caption,
        "hashtags":    hashtags,
        "titres":      titres,
    }


def save_metadata(script_data: dict, video_path: str,
                  output_dir: Path) -> Path:
    """Écrit output/metadata.json et le retourne."""
    meta = build_metadata(script_data, video_path)
    path = output_dir / "metadata.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"  💾 Métadonnées de publication : {path}")
    return path
