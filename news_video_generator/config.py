"""
config.py — Constantes globales du pipeline : configuration, palette de
couleurs, catégories, formatage de date.

Ne dépend d'aucun autre module du package (base de l'arborescence).
"""
import os
from datetime import datetime

# ─────────────────────────────────────────────────────────────
#  DATE EN FRANÇAIS (indépendant de la locale système)
# ─────────────────────────────────────────────────────────────
# Le runner GitHub Actions n'a pas forcément la locale fr_FR installée,
# ce qui fait afficher les jours/mois en anglais avec strftime("%A")/("%B")
# classique. On formate nous-même pour garantir un affichage en français.
_JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
_MOIS_FR  = ["janvier", "février", "mars", "avril", "mai", "juin",
            "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def date_fr(dt: datetime, with_weekday: bool = True) -> str:
    """Formate une date en français ('vendredi 26 juin 2026'), sans dépendre
    de la locale système."""
    jour = _JOURS_FR[dt.weekday()]
    mois = _MOIS_FR[dt.month - 1]
    if with_weekday:
        return f"{jour} {dt.day} {mois} {dt.year}"
    return f"{dt.day} {mois} {dt.year}"


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
    "MUSIC_VOLUME":  0.126,   # Volume musique de fond (-18dB sous la voix — comble les
                              # pauses naturelles d'edge-tts entre phrases, sans couvrir la voix)
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

# Couleurs d'accent vives par catégorie, pour les badges UI (distinctes des
# couleurs sombres ci-dessus qui servent de fonds) — donne plus de vie et
# de hiérarchie visuelle au tag catégorie tout en restant lisible sur fond sombre
CATEGORY_ACCENT = {
    "politique":     (90, 140, 245),
    "economie":      (60, 200, 130),
    "technologie":   (70, 170, 245),
    "science":       (180, 110, 245),
    "sport":         (245, 140, 60),
    "environnement": (80, 210, 120),
    "sante":         (245, 90, 160),
    "culture":       (245, 175, 60),
    "societe":       (160, 160, 210),
    "monde":         (110, 130, 245),
}

# Mots-clés de secours par catégorie pour le repli Unsplash — choisis
# volontairement NEUTRES et SÛRS (lieux, objets, architecture symbolique)
# pour éviter les photos de manifestations, conflits armés ou contenu
# sensible quand les mots-clés générés par Groq ne donnent rien de pertinent.
CATEGORY_EN = {
    "politique":     "government building architecture",
    "economie":      "stock market office building",
    "technologie":   "computer technology office",
    "science":       "laboratory research microscope",
    "sport":         "stadium sports arena",
    "environnement": "nature landscape forest",
    "sante":         "hospital medical equipment",
    "culture":       "museum art gallery",
    "societe":       "city street architecture",
    "monde":         "world map globe",
}
