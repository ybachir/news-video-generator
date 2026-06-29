"""
subtitles.py — Génération du filtre ffmpeg pour les sous-titres animés
mot par mot (style "karaoke"), calés sur le vrai timing vocal capturé par
edge-tts (voir audio.py).
"""
import os

from PIL import Image, ImageDraw, ImageFont


def _sanitize_word_timings(words: list[dict]) -> list[dict]:
    """
    Nettoie les timings de mots avant génération du filtre ffmpeg :
    - garantit start < end pour chaque mot (sinon les expressions
      between() peuvent devenir incohérentes et produire un rendu
      avec un calque dans un état indéterminé)
    - garantit qu'un mot ne commence jamais avant la fin du mot précédent
      (chevauchements possibles avec les imprécisions d'edge-tts)
    """
    clean = []
    prev_end = 0.0
    for w in words:
        start = max(w["start"], prev_end)
        end   = max(w["end"], start + 0.05)   # durée minimale de 50ms
        clean.append({"word": w["word"], "start": start, "end": end})
        prev_end = end
    return clean


def generate_subtitle_filter(words: list[dict], W: int, H: int) -> str:
    """
    Génère un filtre ffmpeg drawtext pour sous-titres animés mot par mot,
    calés sur le VRAI timing vocal (word_timings issus d'edge-tts WordBoundary,
    ou estimation pondérée en fallback).

    Principe (un seul rendu par mot à chaque instant — jamais deux calques
    superposés sur le même mot, ce qui créait un effet de "double texte"
    visible surtout avec le zoom Ken Burns) :
    - Chaque mot du groupe est dessiné en BLANC pendant toute la durée du
      groupe, SAUF pendant sa propre fenêtre de prononciation où il est
      dessiné en DORÉ à la place — jamais les deux en même temps.
    - Position de chaque mot mesurée au pixel exact via PIL (pas d'estimation,
      pas de dérive avec une police non-monospace).
    - Timings validés/nettoyés en amont (voir _sanitize_word_timings) pour
      éviter tout état incohérent en cas de chevauchement entre mots.
    - Le nombre de calques par mot est volontairement minimal (un calque
      "groupe entier" + un calque "mot actif" par mot) : un filtre trop
      long (15000+ caractères, 70+ instances drawtext) s'est montré
      instable sur le runner GitHub Actions, produisant occasionnellement
      un mot rendu avec une police/contour incohérent.

    `words` : liste de {"word": str, "start": float, "end": float} en secondes.
    Retourne une string filtre ffmpeg prête à injecter dans -vf (ou "" si pas
    de mots).
    """
    if not words:
        return ""

    words = _sanitize_word_timings(words)

    GROUP_SIZE = 3
    groups = [words[i:i + GROUP_SIZE] for i in range(0, len(words), GROUP_SIZE)]

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    font_path = next((p for p in font_candidates if os.path.exists(p)), "")
    font_opt  = f"fontfile={font_path}:" if font_path else ""

    FONT_SIZE = 50
    try:
        pil_font = ImageFont.truetype(font_path, FONT_SIZE) if font_path else ImageFont.load_default()
    except Exception:
        pil_font = ImageFont.load_default()
    _measure_img  = Image.new("RGB", (10, 10))
    _measure_draw = ImageDraw.Draw(_measure_img)

    def _text_w(s: str) -> int:
        bb = _measure_draw.textbbox((0, 0), s, font=pil_font)
        return bb[2] - bb[0]

    def _escape(s: str) -> str:
        return (s
            .replace("\\", "\\\\")
            .replace("'",  "’")
            .replace(":",  "\\:")
            .replace(",",  "\\,")
            .replace("[",  "\\[")
            .replace("]",  "\\]")
            .replace("(",  "\\(")
            .replace(")",  "\\)")
        )

    y_sub = H - 195   # bande unique des sous-titres, juste au-dessus de la source

    filters = []
    for grp in groups:
        grp_start = grp[0]["start"]
        grp_end   = grp[-1]["end"]
        grp_text  = " ".join(w["word"] for w in grp)
        grp_w     = _text_w(grp_text)
        grp_x0    = f"(w-{grp_w})/2"   # x du début du texte une fois centré

        # Calque de base : le groupe ENTIER en blanc, affiché pendant toute
        # la durée du groupe (un seul calque, pas un par mot — réduit
        # fortement le nombre total de filtres chaînés)
        filters.append(
            f"drawtext={font_opt}"
            f"text='{_escape(grp_text)}':"
            f"fontsize={FONT_SIZE}:fontcolor=white:borderw=3:bordercolor=black:"
            f"box=1:boxcolor=black@0.55:boxborderw=14:"
            f"x={grp_x0}:y={y_sub}:"
            f"enable='between(t,{grp_start:.3f},{grp_end:.3f})'"
        )

        # Mot actif : redessiné en doré PAR-DESSUS, au même borderw exact
        # que le calque blanc (sinon la bounding box change de taille selon
        # l'épaisseur du contour, ce qui décale verticalement le texte)
        prefix = ""
        for w in grp:
            offset_px = _text_w(prefix)
            x_expr    = f"({grp_x0})+{offset_px}"
            filters.append(
                f"drawtext={font_opt}"
                f"text='{_escape(w['word'])}':"
                f"fontsize={FONT_SIZE}:fontcolor=#F5C518:borderw=3:bordercolor=#3a2c00:"
                f"x={x_expr}:y={y_sub}:"
                f"enable='between(t,{w['start']:.3f},{w['end']:.3f})'"
            )
            prefix += w["word"] + " "

    return ",".join(filters)
