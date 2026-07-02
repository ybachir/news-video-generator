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
    W, H, date_fr,
)
from .news import (
    RSS_FEEDS, fetch_rss_raw, structure_with_groq, get_news, _demo_news,
)
from .photos import (
    SENSITIVE_TERMS, _unsplash_search, _filter_sensitive_keywords,
    download_unsplash_photo, create_styled_background, get_photos,
)
from .audio import (
    EDGE_TTS_VOICE, EDGE_TTS_RATE, EDGE_TTS_RETRIES, EDGE_TTS_TIMEOUT,
    text_to_wav_edge, text_to_wav_espeak, wav_to_mp3,
    _estimate_word_timings, make_audio, generate_all_audio,
)
from .render import (
    _fonts, _wrap, _draw_gold_line, _draw_newspaper_icon,
    render_intro, render_news_frame, render_outro,
)
from .subtitles import _sanitize_word_timings, build_ass
from .video import (
    get_music_path, mix_background_music, validate_mp4, cleanup_frames,
    build_video,
)
from .metadata import build_metadata, save_metadata
from .speech import humanize_for_speech, humanize_script
from .worldcup import (
    WC_RSS_FEEDS, fetch_worldcup_rss, structure_worldcup_with_groq,
    get_worldcup_news, _demo_worldcup,
)

__all__ = [
    "CONFIG", "PALETTE", "CATEGORY_COLORS", "CATEGORY_ACCENT", "CATEGORY_EN",
    "W", "H", "date_fr",
    "RSS_FEEDS", "fetch_rss_raw", "structure_with_groq", "get_news",
    "SENSITIVE_TERMS", "download_unsplash_photo", "create_styled_background", "get_photos",
    "EDGE_TTS_VOICE", "EDGE_TTS_RATE", "EDGE_TTS_RETRIES", "EDGE_TTS_TIMEOUT",
    "text_to_wav_edge", "text_to_wav_espeak", "wav_to_mp3", "make_audio", "generate_all_audio",
    "render_intro", "render_news_frame", "render_outro",
    "build_ass",
    "get_music_path", "mix_background_music", "validate_mp4", "cleanup_frames", "build_video",
    "build_metadata", "save_metadata",
    "humanize_for_speech", "humanize_script",
    "WC_RSS_FEEDS", "get_worldcup_news",
    "main",
]


def main():
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║        📰 NEWS VIDEO GENERATOR — Pipeline 100% Gratuit              ║
║        RSS → Groq → Photos → edge-tts → ffmpeg → MP4 9:16           ║
╚══════════════════════════════════════════════════════════════════════╝
""")
    t0 = time.time()

    output_dir = Path(CONFIG["OUTPUT_DIR"])
    photos_dir = output_dir / "photos"
    audio_dir  = output_dir / "audio"
    for d in [output_dir, photos_dir, audio_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. News — thème standard (journal) ou édition spéciale (worldcup)
    theme = CONFIG.get("THEME", "journal")
    if theme == "worldcup":
        CONFIG.setdefault("EDITION_TOP",    "SPÉCIAL")
        CONFIG.setdefault("EDITION_BOTTOM", "MONDIAL 2026")
        CONFIG.setdefault("EDITION_BRAND",  "SPÉCIAL MONDIAL 2026")
        CONFIG.setdefault("FILE_PREFIX",    "mondial")
        CONFIG.setdefault("EDITION_STYLE",  "worldcup")   # intro ballon + tricolore
        script_data = get_worldcup_news(CONFIG)
    else:
        script_data = get_news(CONFIG)
    if not script_data.get("news"):
        print("❌ Aucune news disponible.")
        sys.exit(1)

    script_path = output_dir / f"script_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(script_data, f, ensure_ascii=False, indent=2)
    print(f"\n  💾 Script : {script_path}")

    # 2. Photos
    photo_paths = get_photos(script_data, CONFIG, photos_dir)

    # 3. Audio
    segments = generate_all_audio(script_data, CONFIG, audio_dir)

    # 4. Vidéo
    try:
        video_path = build_video(segments, photo_paths, script_data, CONFIG, output_dir)
    except RuntimeError as e:
        print(f"\n❌ PIPELINE ÉCHOUÉ : {e}")
        sys.exit(1)

    # 5. Musique de fond (optionnel)
    music_path = get_music_path(output_dir)
    if music_path and CONFIG["MUSIC_VOLUME"] > 0:
        print(f"\n🎵 ÉTAPE 5 — Mixage musique de fond ({music_path})...")
        mixed_path = video_path.replace(".mp4", "_music.mp4")
        ok = mix_background_music(
            video_path, music_path, CONFIG["MUSIC_VOLUME"], mixed_path
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
    save_metadata(script_data, video_path, output_dir)

    elapsed = time.time() - t0
    mins, secs = divmod(int(elapsed), 60)
    size_mb = os.path.getsize(video_path) / 1_000_000
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║  ✅ PIPELINE TERMINÉ en {mins}m{secs:02d}s
║
║  📹 Vidéo  → {video_path} ({size_mb:.1f} MB)
║  📋 Script → {script_path}
╚══════════════════════════════════════════════════════════════════════╝
""")
    return video_path


if __name__ == "__main__":
    main()
