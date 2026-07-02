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


def render_intro(text: str, fonts: dict,
                 top: str = "JOURNAL", bottom: str = "DU MONDE") -> np.ndarray:
    """Écran d'intro : fond sombre, logo centré, glow doré diffus.

    `top`/`bottom` : lignes de la marque (paramétrées pour permettre des
    éditions spéciales, ex. SPÉCIAL / MONDIAL 2026). Si la ligne dorée est
    trop large pour la carte, on rétrograde automatiquement la police."""
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

    # Ligne du haut (blanc)
    draw.text((W // 2, H // 2 - 80), top,
              font=fonts["bold_lg"], fill=(*PALETTE["white"], 255), anchor="mm")

    # Ligne du bas en doré — police réduite automatiquement si trop large
    # pour la carte (ex: "MONDIAL 2026" plus long que "DU MONDE")
    bottom_font = fonts["bold_xl"]
    if draw.textbbox((0, 0), bottom, font=bottom_font)[2] > W - 220:
        bottom_font = fonts["bold_lg"]
    draw.text((W // 2, H // 2 + 20), bottom,
              font=bottom_font, fill=(*PALETTE["gold"], 255), anchor="mm")

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


# Couleurs des trois pays hôtes du Mondial 2026 (thème de l'édition spéciale)
WC_COLORS = {
    "red":   (216, 30, 5),     # Canada
    "blue":  (10, 49, 97),     # États-Unis
    "green": (0, 104, 71),     # Mexique
}


def _draw_soccer_ball(img: Image.Image, cx: int, cy: int, r: int) -> Image.Image:
    """Ballon de football stylisé dessiné en vectoriel (design ORIGINAL —
    le logo officiel FIFA est une marque déposée qu'on ne peut pas
    reproduire) : sphère claire, pentagone central noir, 5 pans noirs en
    périphérie reliés par les coutures, le tout découpé au cercle."""
    import math
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d     = ImageDraw.Draw(layer)

    # Sphère
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(244, 244, 248, 255))

    def pent(pcx, pcy, pr, rot):
        return [(pcx + pr * math.cos(math.radians(rot + k * 72)),
                 pcy + pr * math.sin(math.radians(rot + k * 72))) for k in range(5)]

    # Pentagone central (pointe vers le haut)
    center_pts = pent(cx, cy, r * 0.38, -90)
    d.polygon(center_pts, fill=(18, 18, 24, 255))

    # 5 pans périphériques + coutures depuis les sommets du pentagone
    for k in range(5):
        ang = math.radians(-90 + k * 72)
        px, py = cx + r * 0.98 * math.cos(ang), cy + r * 0.98 * math.sin(ang)
        d.polygon(pent(px, py, r * 0.30, math.degrees(ang) + 36),
                  fill=(18, 18, 24, 255))
        vx, vy = center_pts[k]
        d.line([vx, vy, cx + r * 0.72 * math.cos(ang), cy + r * 0.72 * math.sin(ang)],
               fill=(18, 18, 24, 255), width=max(3, r // 22))

    # Découpe circulaire + contour
    mask = Image.new("L", img.size, 0)
    ImageDraw.Draw(mask).ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    layer.putalpha(Image.composite(layer.split()[3], Image.new("L", img.size, 0), mask))
    out = Image.alpha_composite(img, layer)
    ImageDraw.Draw(out).ellipse([cx - r, cy - r, cx + r, cy + r],
                                outline=(*PALETTE["gold"], 220), width=4)
    return out


def render_intro_worldcup(text: str, fonts: dict,
                          top: str = "SPÉCIAL",
                          bottom: str = "MONDIAL 2026") -> np.ndarray:
    """Intro de l'édition Coupe du Monde 2026 : ballon vectoriel, bandes
    tricolores des pays hôtes (Canada/USA/Mexique), or du template."""
    img  = Image.new("RGB", (W, H), PALETTE["bg"])
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        draw.line([(0, y), (W, y)],
                  fill=(int(PALETTE["bg"][0] + t * 6),
                        int(PALETTE["bg"][1] + t * 12),
                        int(PALETTE["bg"][2] + t * 10)))

    img  = img.convert("RGBA")
    draw = ImageDraw.Draw(img)

    # Bandes haut/bas tricolores (tiers rouge / bleu / vert)
    third = W // 3
    for i, c in enumerate([WC_COLORS["red"], WC_COLORS["blue"], WC_COLORS["green"]]):
        draw.rectangle([i * third, 0,   (i + 1) * third, 8], fill=(*c, 255))
        draw.rectangle([i * third, H-8, (i + 1) * third, H], fill=(*c, 255))

    # Glow doré derrière la carte (identité du template conservée)
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd   = ImageDraw.Draw(glow)
    cx, cy = W // 2, H // 2
    gd.ellipse([cx - 400, cy - 360, cx + 400, cy + 360], fill=(*PALETTE["gold"], 70))
    glow = glow.filter(ImageFilter.GaussianBlur(radius=60))
    img  = Image.alpha_composite(img, glow)

    # Carte centrale
    draw = ImageDraw.Draw(img)
    pad = 70
    cy1, cy2 = H // 2 - 320, H // 2 + 300
    draw.rounded_rectangle([pad, cy1, W - pad, cy2],
                            radius=28, fill=(*PALETTE["bg2"], 235))

    # Ballon
    img  = _draw_soccer_ball(img, W // 2, H // 2 - 190, 88)
    draw = ImageDraw.Draw(img)

    # Typographie
    draw.text((W // 2, H // 2 - 40), top,
              font=fonts["bold_lg"], fill=(*PALETTE["white"], 255), anchor="mm")
    bottom_font = fonts["bold_xl"]
    if draw.textbbox((0, 0), bottom, font=bottom_font)[2] > W - 220:
        bottom_font = fonts["bold_lg"]
    draw.text((W // 2, H // 2 + 60), bottom,
              font=bottom_font, fill=(*PALETTE["gold"], 255), anchor="mm")

    # Barre tricolore sous le titre (3 segments arrondis)
    bw, bh, gap = 90, 10, 14
    x0 = W // 2 - (3 * bw + 2 * gap) // 2
    yb = H // 2 + 130
    for i, c in enumerate([WC_COLORS["red"], WC_COLORS["blue"], WC_COLORS["green"]]):
        draw.rounded_rectangle([x0 + i * (bw + gap), yb,
                                x0 + i * (bw + gap) + bw, yb + bh],
                               radius=5, fill=(*c, 255))

    # Date
    date_str = date_fr(datetime.now()).upper()
    draw.text((W // 2, yb + 48), date_str,
              font=fonts["regular_sm"], fill=(*PALETTE["gray"], 200), anchor="mm")

    # Accroche
    lines = _wrap(text, fonts["regular_md"], W - 160, draw)
    y0 = yb + 105
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
        # Photo PLEINE luminosité, nette (demande utilisateur : suppression
        # de toutes les couches de flou et d'assombrissement — brightness,
        # blur et vignette radiale retirés). La lisibilité du texte est
        # assurée uniquement par le bandeau compact du bas + les ombres
        # portées + la boîte semi-transparente des sous-titres.
    except Exception:
        photo = Image.new("RGB", (W, H), PALETTE["bg"])

    img = photo.convert("RGBA")

    # ── Bandeau bas compact (seule couche sombre restante) ──
    # Ne couvre que la zone texte (~30% inférieurs) au lieu de 55% de
    # l'image : la photo reste intacte sur toute sa partie utile.
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    grad_start = H - 580
    for y in range(grad_start, H):
        t     = (y - grad_start) / (H - grad_start)
        alpha = int(225 * (t ** 0.7))
        od.line([(0, y), (W, y)], fill=(*PALETTE["bg"], alpha))
    img = Image.alpha_composite(img, overlay)
    draw = ImageDraw.Draw(img)

    # ── Barre top ──
    draw.rectangle([0, 0, W, 5], fill=(*PALETTE["gold"], 255))
    # Date dans une pilule (photo désormais pleine luminosité : un texte
    # gris nu deviendrait illisible sur un ciel clair)
    now = datetime.now().strftime("%d/%m/%Y  %H:%M")
    nb  = draw.textbbox((0, 0), now, font=fonts["regular_xs"])
    nw_ = nb[2] - nb[0]
    draw.rounded_rectangle([W // 2 - nw_ // 2 - 18, 14,
                            W // 2 + nw_ // 2 + 18, 48],
                           radius=17, fill=(*PALETTE["bg2"], 200))
    draw.text((W // 2, 30), now,
              font=fonts["regular_xs"], fill=(*PALETTE["gray"], 230), anchor="mm")

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


def render_outro(text: str, fonts: dict,
                 brand: str = "JOURNAL DU MONDE") -> np.ndarray:
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
    draw.text((W // 2, H // 2 - 60), brand,
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
