"""
subtitles.py — Sous-titres animés, refaits de zéro au format ASS (libass).

Pourquoi ASS plutôt que des chaînes de drawtext ?
- L'ancien système générait 20 à 70 filtres drawtext chaînés par clip :
  échappements manuels fragiles (apostrophes, virgules, crochets),
  instabilité documentée sur le runner CI, boîte noire clignotant à
  chaque groupe, et coupures arbitraires tous les 3 mots.
- ASS est LE format professionnel de sous-titrage stylé : ffmpeg le rend
  nativement via libass (un seul filtre `ass=fichier`), l'échappement est
  trivial, le rendu est stable et identique partout.

Design :
- Groupement par PHRASES : on coupe sur la ponctuation forte, sur les
  pauses vocales réelles (> 0.35 s entre deux mots) et au-delà de
  4 mots / ~26 caractères — les sous-titres épousent le rythme de la voix.
- Karaoké propre : tout le groupe affiché en blanc, le mot prononcé
  passe en doré (#F5C518) pendant sa fenêtre exacte. Un évènement ASS
  par mot, texte identique au pixel près → aucun scintillement, seule
  la couleur change.
- Fondu d'apparition/disparition par groupe (120 ms / 100 ms).
- Blanc gras, contour noir épais, ombre légère, pas de boîte opaque :
  lisible sur photo claire comme sombre, sans masquer l'image.
"""
from pathlib import Path

# Or du template (#F5C518) au format ASS (&HBBGGRR&)
GOLD_ASS  = r"\c&H18C5F5&"
WHITE_ASS = r"\c&HFFFFFF&"

MAX_WORDS_PER_GROUP = 5    # 5 (pas 4) : "France 2 à 1 Brésil." reste entier
MAX_CHARS_PER_GROUP = 26
PAUSE_BREAK_S       = 0.35   # silence entre 2 mots qui force un nouveau groupe
STRONG_PUNCT        = ".:;!?…"


def _sanitize_word_timings(words: list[dict]) -> list[dict]:
    """Nettoie les timings : start strictement croissants, durée min 50 ms,
    aucun chevauchement (edge-tts peut produire de légères imprécisions)."""
    clean = []
    prev_end = 0.0
    for w in words:
        token = str(w.get("word", "")).strip()
        if not token:
            continue
        start = max(float(w["start"]), prev_end)
        end   = max(float(w["end"]), start + 0.05)
        clean.append({"word": token, "start": start, "end": end})
        prev_end = end
    return clean


def _group_words(words: list[dict]) -> list[list[dict]]:
    """Groupes en forme de phrases : coupe sur ponctuation forte, pause
    vocale réelle, ou dépassement de taille — jamais au milieu d'un souffle."""
    groups, current, chars = [], [], 0
    for w in words:
        if current:
            gap        = w["start"] - current[-1]["end"]
            prev_punct = current[-1]["word"][-1:] in STRONG_PUNCT
            too_big    = (len(current) >= MAX_WORDS_PER_GROUP
                          or chars + 1 + len(w["word"]) > MAX_CHARS_PER_GROUP)
            if prev_punct or gap > PAUSE_BREAK_S or too_big:
                groups.append(current)
                current, chars = [], 0
        current.append(w)
        chars += (1 if chars else 0) + len(w["word"])
    if current:
        groups.append(current)
    return groups


def _ts(seconds: float) -> str:
    """Timestamp ASS : H:MM:SS.cc"""
    seconds = max(0.0, seconds)
    h  = int(seconds // 3600)
    m  = int(seconds % 3600 // 60)
    s  = int(seconds % 60)
    cs = int(round(seconds % 1 * 100))
    if cs == 100:
        s, cs = s + 1, 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    """Échappement ASS : seules les accolades sont significatives."""
    return text.replace("{", "(").replace("}", ")").replace("\n", " ")


_ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,DejaVu Sans,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,3,2,2,70,70,175,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_ass(words: list[dict], out_path: str | Path) -> str | None:
    """Écrit le fichier .ass karaoké pour un segment.

    Un évènement Dialogue par mot : le texte complet du groupe, avec le
    mot actif encadré en doré. Le premier évènement du groupe porte le
    fondu d'entrée, le dernier le fondu de sortie.
    Retourne le chemin écrit, ou None si aucun mot exploitable."""
    words = _sanitize_word_timings(words)
    if not words:
        return None

    lines = [_ASS_HEADER]
    for grp in _group_words(words):
        last = len(grp) - 1
        for j, w in enumerate(grp):
            fad_in  = 120 if j == 0    else 0
            fad_out = 100 if j == last else 0
            fad = f"{{\\fad({fad_in},{fad_out})}}" if (fad_in or fad_out) else ""
            parts = []
            for k, other in enumerate(grp):
                token = _esc(other["word"])
                if k == j:
                    parts.append(f"{{{GOLD_ASS}}}{token}{{{WHITE_ASS}}}")
                else:
                    parts.append(token)
            lines.append(
                f"Dialogue: 0,{_ts(w['start'])},{_ts(w['end'])},Sub,,0,0,0,,"
                f"{fad}{' '.join(parts)}"
            )

    out_path = Path(out_path)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(out_path)
