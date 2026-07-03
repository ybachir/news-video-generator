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


def build_metadata(script_data: dict, video_path: str) -> dict:
    """Assemble les métadonnées de publication à partir du script du jour."""
    date_str = date_fr(datetime.now(), with_weekday=False)
    titres   = [item.get("titre", "") for item in script_data.get("news", [])]

    hashtags = script_data.get("hashtags") or DEFAULT_HASHTAGS
    hashtags = [h.lstrip("#").strip() for h in hashtags if h.strip()][:10]

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
