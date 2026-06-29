"""
render.py — ÉTAPE 4 : Rendu visuel des écrans (intro / news / outro).

Template premium sombre/doré, dessiné avec PIL. Chaque fonction `render_*`
retourne un frame numpy prêt à être encodé par ffmpeg (voir video.py).
"""
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np

from .config import W, H, PALETTE, CATEGORY_ACCENT, date_fr


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
    """Écran d'intro : fond sombre, logo centré, glow doré diffus."""
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

    # ── Glow doré diffus derrière la carte (remplace la bordure nette,
    # look plus organique/premium que des rectangles à bords francs) ──
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    cx, cy = W // 2, H // 2
    gd.ellipse([cx - 380, cy - 320, cx + 380, cy + 320], fill=(*PALETTE["gold"], 70))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
    img  = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # Carte centrale — fond plein, sans bordure nette (le glow ci-dessus
    # fait le travail de mise en valeur)
    pad = 70
    cy1, cy2 = H // 2 - 280, H // 2 + 280
    draw.rounded_rectangle([pad, cy1, W - pad, cy2],
                            radius=28, fill=(*PALETTE["bg2"], 235))

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
    date_str = date_fr(datetime.now()).upper()
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

    # ── Vignette radiale légère (look plus cinématographique) ──
    img = photo.convert("RGBA")
    vignette = Image.new("L", (W, H), 0)
    vd = ImageDraw.Draw(vignette)
    max_dist = ((W / 2) ** 2 + (H / 2) ** 2) ** 0.5
    cx0, cy0 = W / 2, H * 0.42
    # Dessiné par anneaux concentriques (rapide, pas pixel-par-pixel)
    n_rings = 40
    for i in range(n_rings):
        t = i / n_rings
        r = max_dist * (1 - t)
        alpha = int(70 * t ** 1.6)
        vd.ellipse([cx0 - r, cy0 - r, cx0 + r, cy0 + r], fill=alpha)
    vignette = vignette.filter(ImageFilter.GaussianBlur(radius=40))
    black_layer = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    img = Image.composite(black_layer, img, vignette)

    # ── Overlay dégradé bas ──
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

    # ── Badge numéro (cercle doré avec ombre portée, plus de profondeur) ──
    n  = seg["index"]
    cx, cy, r = 76, 100, 54
    draw.ellipse([cx - r + 4, cy - r + 4, cx + r + 4, cy + r + 4], fill=(0, 0, 0, 90))
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*PALETTE["gold"], 240))
    draw.text((cx, cy), str(n),
              font=fonts["bold_lg"], fill=(*PALETTE["bg"], 255), anchor="mm")

    # ── Tag catégorie (pilule douce + puce ronde colorée, pas de
    # rectangle à bordure nette — cohérent avec le style plus organique) ──
    cat        = seg.get("categorie", "monde")
    cat_tag    = cat.upper()
    cat_accent = CATEGORY_ACCENT.get(cat, PALETTE["gold"])
    bb      = draw.textbbox((0, 0), cat_tag, font=fonts["regular_sm"])
    tag_text_w = bb[2] - bb[0]
    tag_w   = tag_text_w + 50   # +50 pour la puce ronde + espacements
    tag_x   = W - tag_w - 20
    draw.rounded_rectangle([tag_x, 18, W - 20, 58],
                            radius=20, fill=(*PALETTE["bg2"], 225))
    dot_cx = tag_x + 22
    draw.ellipse([dot_cx - 6, 38 - 6, dot_cx + 6, 38 + 6], fill=(*cat_accent, 255))
    draw.text((tag_x + 40, 38), cat_tag,
              font=fonts["regular_sm"], fill=(*cat_accent, 255), anchor="lm")

    # ── Zone texte bas ──
    pad  = 44
    y    = H - 420

    # Titre (blanc, gras, avec ombre portée bien visible pour mieux se
    # détacher de la photo) — max 2 lignes pour garder l'espace nécessaire
    # aux sous-titres animés juste en dessous
    title_lines = _wrap(seg["titre"], fonts["bold_lg"], W - pad * 2, draw)
    for line in title_lines[:2]:
        draw.text((pad + 5, y + 5), line,
                  font=fonts["bold_lg"], fill=(0, 0, 0, 190))   # ombre
        draw.text((pad, y), line,
                  font=fonts["bold_lg"], fill=(*PALETTE["white"], 255))
        y += 70

    # Ligne dorée séparatrice
    _draw_gold_line(draw, pad, y + 6, pad + 100)
    y += 28

    # NOTE : le résumé n'est plus dessiné statiquement ici — il est
    # remplacé par les sous-titres animés mot par mot (generate_subtitle_filter,
    # voir subtitles.py), appliqués en post-traitement ffmpeg avec le vrai
    # timing vocal.

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
    """Écran outro : CTA abonnement + palette premium, glow doré cohérent
    avec l'intro."""
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

    # ── Glow doré diffus (cohérent avec l'intro) ──
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    cx, cy = W // 2, H // 2
    gd.ellipse([cx - 360, cy - 300, cx + 360, cy + 300], fill=(*PALETTE["gold"], 70))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
    img  = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    pad = 70
    draw.rounded_rectangle([pad, H // 2 - 260, W - pad, H // 2 + 260],
                            radius=28, fill=(*PALETTE["bg2"], 230))

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
