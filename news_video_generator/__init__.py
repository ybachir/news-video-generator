#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║        📰 NEWS VIDEO GENERATOR — Journal Automatique FR              ║
║        Actualités → Résumé IA → Photos → Voix → Vidéo 9:16          ║
╚══════════════════════════════════════════════════════════════════════╝

Pipeline 100% gratuit :
  1. RSS feeds  →  résumé structuré via Groq (Llama 3, gratuit)
  2. Photos     →  Unsplash (gratuit) ou fonds générés localement
  3. Audio      →  edge-tts (Microsoft Neural, gratuit) ou espeak fallback
  4. Vidéo      →  ffmpeg direct (rapide) + template premium sombre/doré

Variables d'environnement (.env ou export) :
    GROQ_API_KEY   → https://console.groq.com  (gratuit, 14 400 req/jour)
    UNSPLASH_KEY   → https://unsplash.com/developers (optionnel, 50 req/h)

Architecture du package (voir chaque module pour le détail) :
    config.py     — constantes, palette, config pipeline, date FR
    news.py       — ÉTAPE 1 : collecte RSS + structuration Groq
    photos.py     — ÉTAPE 2 : Unsplash + fonds générés
    audio.py      — ÉTAPE 3 : synthèse vocale edge-tts / espeak
    render.py     — ÉTAPE 4a : rendu visuel PIL (intro/news/outro)
    subtitles.py  — ÉTAPE 4b : sous-titres karaoké ASS (libass)
    video.py       — ÉTAPE 4c/5 : montage ffmpeg, musique, validation

Ce fichier __init__.py réexporte l'intégralité de l'API publique (et
quelques fonctions privées utilisées par test_pipeline.py) pour que
`import news_video_generator as m` continue de fonctionner exactement
comme avant le découpage en modules — aucun appelant externe
(run_pipeline.py, test_pipeline.py) n'a besoin d'être modifié.
"""
import os
import sys
import json
import time
from pathlib import Path
from datetime import datetime

# ── Réexport de l'API publique (ordre = ordre des étapes du pipeline) ──
from .config import (
    CONFIG, PALETTE, CATEGORY_COLORS, CATEGORY_ACCENT, CATEGORY_EN,
    W, H, LANDSCAPE_W, LANDSCAPE_H, date_fr,
)
from .news import (
    RSS_FEEDS, fetch_rss_raw, structure_with_groq, get_news, _demo_news,
    RSS_MAX_AGE_HOURS, _entry_age_hours, _fmt_age_fr,
)
from .photos import (
    SENSITIVE_TERMS, _search_candidates, _score_candidate, _filter_sensitive_keywords,
    find_best_photo, create_styled_background, get_photos,
)
from .audio import (
    EDGE_TTS_VOICE, EDGE_TTS_RATE, EDGE_TTS_RETRIES, EDGE_TTS_TIMEOUT,
    text_to_wav_edge, text_to_wav_espeak, wav_to_mp3,
    _estimate_word_timings, make_audio, generate_all_audio,
)
from .render import (
    _fonts, _wrap, _draw_gold_line, _draw_newspaper_icon,
    render_intro, render_news_frame, render_outro,
    render_intro_landscape, render_news_frame_landscape, render_outro_landscape,
)
from .subtitles import _sanitize_word_timings, build_ass
from .video import (
    get_music_path, mix_background_music, validate_mp4, cleanup_frames,
    build_video,
)
from .metadata import build_metadata, save_metadata, BRAND_HASHTAG, ALWAYS_ON_HASHTAGS
from .speech import humanize_for_speech, humanize_script
from .worldcup import (
    WC_RSS_FEEDS, fetch_worldcup_rss, structure_worldcup_with_groq,
    get_worldcup_news, _demo_worldcup,
)
from .france import (
    FR_RSS_FEEDS, fetch_france_rss, structure_france_with_groq,
    get_france_news, _demo_france,
)
from .topics import (
    MIN_TOPICS, MAX_TOPICS, fetch_topic_pool, detect_daily_topics,
    structure_topic_deepdive_with_groq, get_daily_deepdive_scripts, _demo_topics,
    _merge_similar_topics,
)
from .weekly import (
    WEEKLY_MAX_AGE_HOURS, WEEKLY_MIN_SEGMENTS, WEEKLY_MAX_SEGMENTS,
    fetch_weekly_france_pool, structure_weekly_with_groq,
    get_weekly_france_news, _demo_weekly,
)
from .monthly import (
    default_period as monthly_default_period,
    get_monthly_france_news, _demo_monthly,
)

__all__ = [
    "CONFIG", "PALETTE", "CATEGORY_COLORS", "CATEGORY_ACCENT", "CATEGORY_EN",
    "W", "H", "LANDSCAPE_W", "LANDSCAPE_H", "date_fr",
    "RSS_FEEDS", "fetch_rss_raw", "structure_with_groq", "get_news",
    "RSS_MAX_AGE_HOURS", "_fmt_age_fr",
    "SENSITIVE_TERMS", "find_best_photo", "create_styled_background", "get_photos",
    "EDGE_TTS_VOICE", "EDGE_TTS_RATE", "EDGE_TTS_RETRIES", "EDGE_TTS_TIMEOUT",
    "text_to_wav_edge", "text_to_wav_espeak", "wav_to_mp3", "make_audio", "generate_all_audio",
    "render_intro", "render_news_frame", "render_outro",
    "render_intro_landscape", "render_news_frame_landscape", "render_outro_landscape",
    "build_ass",
    "get_music_path", "mix_background_music", "validate_mp4", "cleanup_frames", "build_video",
    "build_metadata", "save_metadata", "BRAND_HASHTAG", "ALWAYS_ON_HASHTAGS",
    "humanize_for_speech", "humanize_script",
    "WC_RSS_FEEDS", "get_worldcup_news",
    "FR_RSS_FEEDS", "get_france_news",
    "MIN_TOPICS", "MAX_TOPICS", "get_daily_deepdive_scripts",
    "WEEKLY_MAX_AGE_HOURS", "WEEKLY_MIN_SEGMENTS", "WEEKLY_MAX_SEGMENTS",
    "get_weekly_france_news",
    "monthly_default_period", "get_monthly_france_news",
    "main",
]


def _run_pipeline_for_script(script_data: dict, config: dict, output_dir: Path) -> str:
    """Exécute les étapes 2 à 6 du pipeline (photos, audio, vidéo, musique,
    métadonnées) pour UN script déjà structuré. Isolée de main() pour être
    réutilisable par le mode 'deepdive', qui appelle cette fonction une
    fois PAR sujet détecté (plusieurs vidéos indépendantes en un seul run)."""
    photos_dir = output_dir / "photos"
    audio_dir  = output_dir / "audio"
    for d in [output_dir, photos_dir, audio_dir]:
        d.mkdir(parents=True, exist_ok=True)

    script_path = output_dir / f"script_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 Script : {script_path}")

    # 2. Photos
    photo_paths = get_photos(script_data, config, photos_dir)

    # 3. Audio
    segments = generate_all_audio(script_data, config, audio_dir)

    # 4. Vidéo
    try:
        video_path = build_video(segments, photo_paths, script_data, config, output_dir)
    except RuntimeError as e:
        print(f"\n❌ PIPELINE ÉCHOUÉ : {e}")
        sys.exit(1)

    # 5. Musique de fond (optionnel)
    music_path = get_music_path(output_dir)
    if music_path and config["MUSIC_VOLUME"] > 0:
        print(f"\n🎵 ÉTAPE 5 — Mixage musique de fond ({music_path})...")
        mixed_path = video_path.replace(".mp4", "_music.mp4")
        ok = mix_background_music(
            video_path, music_path, config["MUSIC_VOLUME"], mixed_path
        )
        if ok and os.path.exists(mixed_path):
            os.replace(mixed_path, video_path)   # remplace la vidéo finale
            print("  ✅ Musique mixée")
        else:
            print("  ⚠️  Mix échoué — vidéo sans musique conservée")
    else:
        print("\n🎵 Pas de musique trouvée — dépose assets/ambient_news.mp3 pour l'activer")

    # 6. Métadonnées de publication (titre YouTube, description, caption IG)
    print("\n📝 ÉTAPE 6 — Métadonnées de publication...")
    save_metadata(script_data, video_path, output_dir, config)

    return video_path


def _main_deepdive(t0: float) -> list[str]:
    """Mode 'ZOOM SUR' : détecte 2 à 4 sujets dominants du jour (recoupés
    par plusieurs sources) et génère une vidéo approfondie DISTINCTE par
    sujet, chacune dans son propre sous-dossier de output/."""
    print("🔎 Édition ZOOM SUR — détection des sujets dominants du jour...")

    output_root = Path(CONFIG["OUTPUT_DIR"])
    output_root.mkdir(parents=True, exist_ok=True)

    topics = get_daily_deepdive_scripts(CONFIG)
    if not topics:
        print("❌ Aucun sujet disponible.")
        sys.exit(1)

    video_paths = []
    for i, item in enumerate(topics, 1):
        script_data = item["script_data"]
        slug        = item["slug"]
        bandeau     = script_data.get("bandeau", "L'ACTU DU JOUR")[:24]

        print(f"\n╔══════════ SUJET {i}/{len(topics)} — {bandeau} ══════════╗")

        # Réglages d'édition PROPRES à ce sujet (pas de setdefault : on
        # écrase à chaque itération, sinon le 1er sujet resterait affiché
        # sur les vidéos suivantes).
        CONFIG["EDITION_TOP"]    = "ZOOM SUR"
        CONFIG["EDITION_BOTTOM"] = bandeau
        CONFIG["EDITION_BRAND"]  = "ZOOM SUR L'ACTU"
        CONFIG["FILE_PREFIX"]    = slug
        CONFIG.pop("EDITION_STYLE", None)   # pas d'intro spéciale worldcup ici

        if not script_data.get("news"):
            print(f"  ⚠️  Sujet '{bandeau}' sans contenu — ignoré")
            continue

        video_dir  = output_root / slug
        video_path = _run_pipeline_for_script(script_data, CONFIG, video_dir)
        video_paths.append(video_path)

    if not video_paths:
        print("❌ Aucune vidéo générée.")
        sys.exit(1)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  ✅ ÉDITION ZOOM SUR TERMINÉE en {mins}m{secs:02d}s — {len(video_paths)} vidéo(s)
""")
    for vp in video_paths:
        size_mb = os.path.getsize(vp) / 1_000_000
        print(f"║  📹 {vp} ({size_mb:.1f} MB)")
    print("╚══════════════════════════════════════════════════════════════════════╝\n")

    return video_paths


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║        📰 NEWS VIDEO GENERATOR — Pipeline 100% Gratuit              ║
║        RSS → Groq → Photos → edge-tts → ffmpeg → MP4 9:16           ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    t0 = time.time()

    theme = CONFIG.get("THEME", "journal")

    # Mode 'deepdive' : plusieurs vidéos indépendantes (une par sujet
    # dominant du jour) — pipeline différent de main(), délégué.
    if theme == "deepdive":
        return _main_deepdive(t0)

    output_dir = Path(CONFIG["OUTPUT_DIR"])
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. News — thème standard (journal) ou édition spéciale (worldcup / france / weekly)
    if theme == "worldcup":
        CONFIG.setdefault("EDITION_TOP",    "SPÉCIAL")
        CONFIG.setdefault("EDITION_BOTTOM", "MONDIAL 2026")
        CONFIG.setdefault("EDITION_BRAND",  "SPÉCIAL MONDIAL 2026")
        CONFIG.setdefault("FILE_PREFIX",    "mondial")
        CONFIG.setdefault("EDITION_STYLE",  "worldcup")   # intro ballon + tricolore
        script_data = get_worldcup_news(CONFIG)
    elif theme == "france":
        CONFIG.setdefault("EDITION_TOP",    "SPÉCIAL")
        CONFIG.setdefault("EDITION_BOTTOM", "FRANCE")
        CONFIG.setdefault("EDITION_BRAND",  "SPÉCIAL FRANCE")
        CONFIG.setdefault("FILE_PREFIX",    "france")
        script_data = get_france_news(CONFIG)
    elif theme == "weekly":
        # Vidéo YouTube LONGUE (pas un Short) : format paysage 16:9,
        # aussi longue que nécessaire pour couvrir toute la semaine.
        CONFIG.setdefault("EDITION_TOP",    "RÉCAP")
        CONFIG.setdefault("EDITION_BOTTOM", "DE LA SEMAINE")
        CONFIG.setdefault("EDITION_BRAND",  "RÉCAP HEBDO")
        CONFIG.setdefault("FILE_PREFIX",    "hebdo")
        CONFIG.setdefault("FORMAT",         "landscape")
        script_data = get_weekly_france_news(CONFIG)
    elif theme == "monthly":
        # Vidéo YouTube LONGUE (format paysage 16:9), récap d'un mois
        # calendaire complet — script pré-rédigé (voir monthly.py), pas de
        # scraping RSS (impossible à un mois d'écart).
        CONFIG.setdefault("EDITION_TOP",    "RÉCAP")
        CONFIG.setdefault("EDITION_BOTTOM", "DU MOIS")
        CONFIG.setdefault("EDITION_BRAND",  "RÉCAP MENSUEL")
        CONFIG.setdefault("FILE_PREFIX",    "mensuel")
        CONFIG.setdefault("FORMAT",         "landscape")
        script_data = get_monthly_france_news(CONFIG)
    else:
        # Identité "nouvelle génération" : positionnement des chaînes d'actu
        # les plus vues (l'essentiel, rapide, accessible) — design original
        CONFIG.setdefault("EDITION_TOP",    "L'ESSENTIEL")
        CONFIG.setdefault("EDITION_BOTTOM", "DE L'ACTU")
        CONFIG.setdefault("EDITION_BRAND",  "L'ESSENTIEL DE L'ACTU")
        script_data = get_news(CONFIG)
    if not script_data.get("news"):
        print("❌ Aucune news disponible.")
        sys.exit(1)

    video_path = _run_pipeline_for_script(script_data, CONFIG, output_dir)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    size_mb = os.path.getsize(video_path) / 1_000_000
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  ✅ PIPELINE TERMINÉ en {mins}m{secs:02d}s
║
║  📹 Vidéo  → {video_path} ({size_mb:.1f} MB)
╚══════════════════════════════════════════════════════════════════════╝
""")
    return video_path


if __name__ == "__main__":
    main()
