#!/usr/bin/env python3
"""
test_pipeline.py — Tests complets du pipeline News Video Generator

Usage:
    python3 test_pipeline.py              # Tous les tests
    python3 test_pipeline.py --quick      # Tests rapides (sans vidéo)
    python3 test_pipeline.py --tts        # Test TTS seulement
    python3 test_pipeline.py --video      # Test vidéo complet (lent)
"""

import sys, os, time, json, traceback
from pathlib import Path

# Couleurs terminal
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed = []
failed = []


def test(name: str):
    """Décorateur de test."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            print(f"\n  {BLUE}▶ {name}{RESET}")
            try:
                start = time.time()
                result = fn(*args, **kwargs)
                elapsed = time.time() - start
                print(f"  {GREEN}✅ PASS{RESET} ({elapsed:.2f}s)")
                passed.append(name)
                return result
            except Exception as e:
                print(f"  {RED}❌ FAIL : {e}{RESET}")
                if "--verbose" in sys.argv:
                    traceback.print_exc()
                failed.append(name)
                return None
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────
#  TESTS IMPORTS
# ─────────────────────────────────────────────────────────────

@test("Import news_video_generator")
def test_import():
    import news_video_generator as m
    assert hasattr(m, 'main'), "main() manquant"
    assert hasattr(m, 'get_news'), "get_news() manquant"
    assert hasattr(m, 'get_photos'), "get_photos() manquant"
    assert hasattr(m, 'generate_all_audio'), "generate_all_audio() manquant"
    assert hasattr(m, 'build_video'), "build_video() manquant"
    return m


@test("Import tts_kokoro")
def test_import_tts():
    import tts_kokoro as t
    assert hasattr(t, 'text_to_mp3'), "text_to_mp3() manquant"
    assert hasattr(t, 'generate_all_audio_kokoro'), "generate_all_audio_kokoro() manquant"


@test("Dépendances Python")
def test_deps():
    missing = []
    for pkg in ['moviepy', 'PIL', 'requests', 'feedparser', 'numpy', 'soundfile']:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        raise ImportError(f"Packages manquants : {missing}\nLancer : pip install {' '.join(missing)}")


@test("Dépendances système (espeak-ng, ffmpeg)")
def test_system_deps():
    import subprocess
    for cmd in ['espeak-ng', 'ffmpeg']:
        r = subprocess.run(['which', cmd], capture_output=True)
        if r.returncode != 0:
            raise EnvironmentError(f"{cmd} non trouvé — sudo apt install {cmd}")


# ─────────────────────────────────────────────────────────────
#  TESTS NEWS
# ─────────────────────────────────────────────────────────────

@test("Génération news demo (sans API)")
def test_news_demo():
    import news_video_generator as m
    data = m._demo_news(5)
    assert len(data['news']) == 5, f"Attendu 5 news, got {len(data['news'])}"
    for item in data['news']:
        assert 'titre' in item, "Champ 'titre' manquant"
        assert 'resume' in item, "Champ 'resume' manquant"
        assert 'source' in item, "Champ 'source' manquant"
        assert 'keywords_photo' in item, "Champ 'keywords_photo' manquant"
        assert len(item['keywords_photo']) >= 2, "Minimum 2 keywords photo"
    assert 'intro' in data, "Champ 'intro' manquant"
    assert 'outro' in data, "Champ 'outro' manquant"
    return data


@test("Script fallback (sans Anthropic API)")
def test_script_fallback():
    import news_video_generator as m
    # _demo_news génère un script complet structuré
    data = m._demo_news(3)
    assert 'news' in data, "Champ 'news' manquant"
    assert len(data['news']) == 3
    assert 'intro' in data, "Champ 'intro' manquant"
    assert 'outro' in data, "Champ 'outro' manquant"
    for item in data['news']:
        assert 'titre' in item
        assert 'resume' in item
        assert 'keywords_photo' in item
    return data


# ─────────────────────────────────────────────────────────────
#  TESTS IMAGES
# ─────────────────────────────────────────────────────────────

@test("Génération fond stylé (placeholder)")
def test_placeholder_image():
    import news_video_generator as m
    from PIL import Image
    out = "/tmp/test_placeholder.jpg"
    m.create_styled_background(["technology", "world", "news"], "technologie", 1, out)
    assert os.path.exists(out), "Fichier non créé"
    img = Image.open(out)
    assert img.size == (m.W, m.H), f"Taille incorrecte : {img.size} vs ({m.W},{m.H})"
    assert os.path.getsize(out) > 10_000, "Fichier trop petit"
    print(f"    → {img.size[0]}×{img.size[1]}px, {os.path.getsize(out)//1024}KB")


@test("Toutes les catégories de couleurs")
def test_category_colors():
    import news_video_generator as m
    categories = list(m.CATEGORY_COLORS.keys())
    assert len(categories) >= 8, f"Seulement {len(categories)} catégories"
    for i, cat in enumerate(categories):
        out = f"/tmp/test_cat_{cat}.jpg"
        m.create_styled_background(["test"], cat, i+1, out)
        assert os.path.exists(out)
    print(f"    → {len(categories)} catégories testées")


@test("Render frame intro")
def test_render_intro():
    import news_video_generator as m
    import numpy as np
    fonts = m._fonts()
    frame = m.render_intro("Bienvenue dans le journal du monde.", fonts)
    assert isinstance(frame, np.ndarray), "Frame doit être un ndarray"
    assert frame.shape == (m.H, m.W, 3), f"Shape incorrect : {frame.shape}"
    print(f"    → Frame {frame.shape[1]}×{frame.shape[0]} RGB")


@test("Render frame news")
def test_render_news():
    import news_video_generator as m
    import numpy as np
    # Créer une image de test
    from PIL import Image
    test_photo = "/tmp/test_news_photo.jpg"
    Image.new("RGB", (800, 1200), (50, 80, 120)).save(test_photo)

    fonts = m._fonts()
    seg = {
        "index": 1, "titre": "Titre de test de l'actualité",
        "text": "Résumé de l'actualité pour le test du rendu visuel.",
        "source": "TestMedia", "categorie": "technologie",
    }
    frame = m.render_news_frame(seg, test_photo, fonts)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (m.H, m.W, 3)
    print(f"    → Frame {frame.shape[1]}×{frame.shape[0]} RGB")


@test("Render frame outro")
def test_render_outro():
    import news_video_generator as m
    import numpy as np
    fonts = m._fonts()
    frame = m.render_outro("Merci et à bientôt.", fonts)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (m.H, m.W, 3)


# ─────────────────────────────────────────────────────────────
#  TESTS AUDIO
# ─────────────────────────────────────────────────────────────

@test("espeak-ng — génération WAV")
def test_espeak_wav():
    import news_video_generator as m
    out = "/tmp/test_espeak.wav"
    ok = m.text_to_wav("Test de synthèse vocale espeak.", out, m.CONFIG)
    assert ok, "espeak n'a pas généré le WAV"
    assert os.path.getsize(out) > 5000, "WAV trop petit"
    print(f"    → WAV {os.path.getsize(out)//1024}KB")


@test("ffmpeg — conversion WAV → MP3")
def test_wav_to_mp3():
    import news_video_generator as m
    wav = "/tmp/test_espeak.wav"
    mp3 = "/tmp/test_espeak.mp3"
    if not os.path.exists(wav):
        m.text_to_wav("Test.", wav, m.CONFIG)
    ok = m.wav_to_mp3(wav, mp3)
    assert ok, "ffmpeg n'a pas converti"
    assert os.path.getsize(mp3) > 1000, "MP3 trop petit"
    print(f"    → MP3 {os.path.getsize(mp3)//1024}KB")


@test("Durée audio mesurable (MoviePy)")
def test_audio_duration():
    from moviepy import AudioFileClip
    mp3 = "/tmp/test_espeak.mp3"
    if not os.path.exists(mp3):
        import news_video_generator as m
        wav = "/tmp/test_espeak.wav"
        m.text_to_wav("Test de durée.", wav, m.CONFIG)
        m.wav_to_mp3(wav, mp3)
    clip = AudioFileClip(mp3)
    dur = clip.duration
    clip.close()
    assert dur > 0.5, f"Durée trop courte : {dur}s"
    assert dur < 30, f"Durée anormalement longue : {dur}s"
    print(f"    → Durée : {dur:.2f}s")


@test("tts_kokoro — text_to_mp3 (espeak fallback)")
def test_tts_kokoro_module():
    import tts_kokoro as t
    out = "/tmp/test_tts_module.mp3"
    mp3, dur = t.text_to_mp3(
        "Numéro un. Ceci est un test complet du module TTS Kokoro.",
        out, tmp_dir="/tmp"
    )
    assert mp3 and os.path.exists(mp3), "MP3 non généré"
    assert dur > 0.5, f"Durée invalide : {dur}"
    print(f"    → {os.path.getsize(mp3)//1024}KB, {dur:.2f}s")


# ─────────────────────────────────────────────────────────────
#  TEST PIPELINE COMPLET
# ─────────────────────────────────────────────────────────────

@test("Pipeline complet 3 news (demo, sans API)")
def test_full_pipeline():
    import news_video_generator as m
    output_dir = Path("/tmp/test_pipeline_output")
    photos_dir = output_dir / "photos"
    audio_dir  = output_dir / "audio"
    for d in [output_dir, photos_dir, audio_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. News
    script_data = m._demo_news(3)
    assert len(script_data['news']) == 3

    # 2. Photos
    photo_paths = m.get_photos(script_data, m.CONFIG, photos_dir)
    assert len(photo_paths) == 3
    for p in photo_paths:
        assert os.path.exists(p), f"Photo manquante : {p}"

    # 3. Audio
    segments = m.generate_all_audio(script_data, m.CONFIG, audio_dir)
    assert len(segments) == 5  # intro + 3 news + outro
    total_dur = sum(s['duration'] for s in segments)
    print(f"    → Audio total : {total_dur:.1f}s")

    # 4. Vidéo
    video_path = m.build_video(segments, photo_paths, script_data, m.CONFIG, output_dir)
    assert os.path.exists(video_path), "Vidéo non créée"
    size_mb = os.path.getsize(video_path) / 1_000_000
    assert size_mb > 0.5, f"Vidéo trop petite : {size_mb:.2f}MB"
    print(f"    → Vidéo : {video_path}")
    print(f"    → Taille : {size_mb:.1f}MB")
    return video_path


# ─────────────────────────────────────────────────────────────
#  MAIN
# ─────────────────────────────────────────────────────────────

def main():
    quick = "--quick" in sys.argv
    tts_only = "--tts" in sys.argv
    video_only = "--video" in sys.argv

    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════╗
║         🧪 NEWS VIDEO GENERATOR — Test Suite              ║
╚══════════════════════════════════════════════════════════╝{RESET}
""")

    if tts_only:
        test_deps()
        test_system_deps()
        test_espeak_wav()
        test_wav_to_mp3()
        test_audio_duration()
        test_tts_kokoro_module()
    elif video_only:
        test_import()
        test_full_pipeline()
    else:
        # Tous les tests
        test_import()
        test_import_tts()
        test_deps()
        test_system_deps()
        test_news_demo()
        test_script_fallback()
        test_placeholder_image()
        test_category_colors()
        test_render_intro()
        test_render_news()
        test_render_outro()
        test_espeak_wav()
        test_wav_to_mp3()
        test_audio_duration()
        test_tts_kokoro_module()
        if not quick:
            test_full_pipeline()

    # ── Résumé ──
    total = len(passed) + len(failed)
    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════╗
║  📊 RÉSULTATS : {len(passed)}/{total} tests passés{RESET}{BOLD}
╠══════════════════════════════════════════════════════════╣{RESET}""")

    if passed:
        for t in passed:
            print(f"  {GREEN}✅ {t}{RESET}")
    if failed:
        print(f"  {BOLD}─── Échecs ───{RESET}")
        for t in failed:
            print(f"  {RED}❌ {t}{RESET}")

    print(f"{BOLD}╚══════════════════════════════════════════════════════════╝{RESET}")

    if failed:
        print(f"\n{RED}⚠️  {len(failed)} test(s) échoué(s). Lance avec --verbose pour les détails.{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}🎉 Tous les tests passent !{RESET}")


if __name__ == "__main__":
    main()
