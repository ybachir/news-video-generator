"""
speech.py — Normalisation du texte pour une lecture TTS fluide.

Problèmes corrigés (demande utilisateur) :
- Les scores "2-1" sont lus "deux tiret un" ou avec une pause bizarre
  → réécrits "2 à 1" (la voix lit naturellement "deux à un", et les
  sous-titres affichent aussi "2 à 1", parfaitement lisible).
- Les abréviations type "RD Congo" sont épelées ou mal prononcées
  → développées en toutes lettres ("République démocratique du Congo").

La normalisation est appliquée au script AVANT la synthèse vocale, donc
la voix, les sous-titres (alignés sur les mots prononcés) et le titre
affiché restent parfaitement cohérents.
"""
import re

# Abréviations développées pour la voix. Ordre important : les formes
# longues d'abord (sinon "RD Congo" serait cassé par un remplacement "RDC").
ABBREVIATIONS = [
    (r"\bRD\s+Congo\b",        "République démocratique du Congo"),
    (r"\bRDC\b",               "République démocratique du Congo"),
    (r"\bÉ\.?-?U\.?\b",        "États-Unis"),
    (r"\bUSA\b",               "États-Unis"),
    (r"\bU\.S\.A\.?\b",        "États-Unis"),
    (r"\bUK\b",                "Royaume-Uni"),
    (r"\bJO\b",                "Jeux olympiques"),
    (r"\bvs\.?\b",             "contre"),
    (r"\bVS\.?\b",             "contre"),
    # Neutre, sans préposition : "aux t.a.b." → "aux tirs au but",
    # "séance de t.a.b." → "séance de tirs au but" (la préposition
    # déjà présente dans la phrase fait le travail)
    (r"\bt\.?a\.?b\b\.?",      "tirs au but"),
    (r"\bkm/h\b",              "kilomètres heure"),
    (r"\bn°\s*",               "numéro "),
    (r"\bN°\s*",               "numéro "),
    (r"(\d)\s*Mds?\s*€",       r"\1 milliards d'euros"),
    (r"(\d)\s*Md€",            r"\1 milliards d'euros"),
    (r"(\d)\s*M€",             r"\1 millions d'euros"),
    (r"\s*&\s*",               " et "),
]

# Score : deux nombres de 1-2 chiffres séparés par un tiret (-, – ou —).
# Limité à 2 chiffres pour NE PAS toucher les saisons/années ("2025-2026")
# ni les périodes ("1914-1918").
_SCORE_RE = re.compile(r"\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\b")


def humanize_for_speech(text: str) -> str:
    """Rend un texte fluide à l'oral : scores '2-1' → '2 à 1',
    abréviations développées. Idempotent (réappliquer ne change rien)."""
    if not text:
        return text
    out = _SCORE_RE.sub(r"\1 à \2", text)
    for pattern, repl in ABBREVIATIONS:
        out = re.sub(pattern, repl, out)
    out = re.sub(r"  +", " ", out)
    return out.strip()


def humanize_script(script_data: dict) -> dict:
    """Applique la normalisation à tout le script (intro, outro, titres,
    résumés) — modifie le dict en place et le retourne."""
    for key in ("intro", "outro"):
        if script_data.get(key):
            script_data[key] = humanize_for_speech(script_data[key])
    for item in script_data.get("news", []):
        for key in ("titre", "resume"):
            if item.get(key):
                item[key] = humanize_for_speech(item[key])
    return script_data
