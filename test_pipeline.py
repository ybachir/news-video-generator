#!/usr/bin/env python3
"""
test_pipeline.py — Tests du pipeline News Video Generator

Usage:
    python3 test_pipeline.py          # Tous les tests (avec vidéo)
    python3 test_pipeline.py --quick  # Tests rapides (sans vidéo)
"""

import sys, os, time, json, traceback
from pathlib import Path

GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

passed, failed = [], []


def test(name: str):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            print(f"\n  {BLUE}▶ {name}{RESET}")
            try:
                start  = time.time()
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


# ── Imports & dépendances ──────────────────────────────────────

@test("Import news_video_generator")
def test_import():
    import news_video_generator as m
    for fn in ["main", "get_news", "get_photos", "generate_all_audio", "build_video"]:
        assert hasattr(m, fn), f"{fn}() manquant"
    return m

@test("Dépendances Python")
def test_deps():
    missing = []
    for pkg in ["PIL", "requests", "feedparser", "numpy"]:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)
    if missing:
        raise ImportError(f"Packages manquants : {missing}")

@test("edge-tts disponible")
def test_edge_tts():
    try:
        import edge_tts
        print(f"    → edge-tts {edge_tts.__version__}")
    except ImportError:
        raise ImportError("edge-tts non installé — pip install edge-tts")

@test("Dépendances système (ffmpeg, espeak-ng)")
def test_system_deps():
    import subprocess
    for cmd in ["ffmpeg", "espeak-ng"]:
        r = subprocess.run(["which", cmd], capture_output=True)
        if r.returncode != 0:
            raise EnvironmentError(f"{cmd} non trouvé")


# ── News ───────────────────────────────────────────────────────

@test("News démo (sans API)")
def test_demo_news():
    import news_video_generator as m
    data = m._demo_news(5)
    assert len(data["news"]) == 5
    for item in data["news"]:
        for field in ["titre", "resume", "source", "categorie", "keywords_photo"]:
            assert field in item, f"Champ '{field}' manquant"
    assert "intro" in data and "outro" in data
    return data

@test("RSS scraping (fetch_rss_raw)")
def test_rss():
    import news_video_generator as m
    articles = m.fetch_rss_raw(10)
    assert len(articles) >= 3, f"Seulement {len(articles)} articles — vérifier la connexion"
    print(f"    → {len(articles)} articles collectés")
    return articles


# ── Visuels ────────────────────────────────────────────────────

@test("Fond premium généré")
def test_background():
    import news_video_generator as m
    from PIL import Image
    out = "/tmp/test_bg.jpg"
    m.create_styled_background(["technology", "world"], "technologie", 1, out)
    assert os.path.exists(out)
    img = Image.open(out)
    assert img.size == (m.W, m.H), f"Taille incorrecte : {img.size}"
    print(f"    → {img.size[0]}×{img.size[1]}px, {os.path.getsize(out)//1024}KB")

@test("Render frame intro")
def test_render_intro():
    import news_video_generator as m
    import numpy as np
    fonts = m._fonts()
    frame = m.render_intro("Bienvenue dans le journal.", fonts)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (m.H, m.W, 3)
    print(f"    → {frame.shape[1]}×{frame.shape[0]} RGB")

@test("Render frame news")
def test_render_news():
    import news_video_generator as m
    from PIL import Image
    import numpy as np
    photo = "/tmp/test_photo.jpg"
    Image.new("RGB", (800, 1200), (30, 50, 80)).save(photo)
    fonts = m._fonts()
    seg = {
        "index": 1, "titre": "Titre de test actualité",
        "text": "Résumé de test pour le rendu visuel.",
        "source": "TestMedia", "categorie": "technologie",
    }
    frame = m.render_news_frame(seg, photo, fonts)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (m.H, m.W, 3)

@test("Render frame outro")
def test_render_outro():
    import news_video_generator as m
    import numpy as np
    fonts = m._fonts()
    frame = m.render_outro("Merci et à bientôt.", fonts)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (m.H, m.W, 3)

@test("Palette dorée présente (template premium)")
def test_palette():
    import news_video_generator as m
    assert m.PALETTE["gold"] == (245, 197, 24), "Couleur or incorrecte"
    assert m.PALETTE["bg"]   == (10, 10, 18),   "Couleur fond incorrecte"
    print(f"    → gold={m.PALETTE['gold']}  bg={m.PALETTE['bg']}")


@test("Métadonnées de publication (build_metadata)")
def test_metadata():
    import news_video_generator as m
    data = m._demo_news(5)
    meta = m.build_metadata(data, "/tmp/journal_test.mp4")
    for field in ["titre_video", "description", "caption", "hashtags", "titres"]:
        assert field in meta, f"Champ '{field}' manquant"
    assert len(meta["titres"]) == 5
    assert len(meta["caption"]) <= 2200, "Caption > limite Meta (2200)"
    assert all(not h.startswith("#") for h in meta["hashtags"])
    print(f"    → titre : {meta['titre_video'][:60]}")


@test("Édition Spécial Coupe du Monde (démo)")
def test_worldcup_demo():
    import news_video_generator as m
    data = m._demo_worldcup(5)
    assert len(data["news"]) == 5
    for item in data["news"]:
        assert item["categorie"] == "sport"
        for field in ["titre", "resume", "source", "keywords_photo"]:
            assert field in item, f"Champ '{field}' manquant"
    assert "titre_video" in data and "hashtags" in data
    meta = m.build_metadata(data, "/tmp/mondial_test.mp4")
    assert "Coupe du Monde" in meta["titre_video"] or "⚽" in meta["titre_video"]
    print(f"    → {meta['titre_video'][:60]}")


@test("Normalisation vocale (scores, abréviations)")
def test_speech():
    import news_video_generator as m
    assert m.humanize_for_speech("France 2-1 Brésil") == "France 2 à 1 Brésil"
    assert "République démocratique du Congo" in m.humanize_for_speech("la RD Congo vote")
    assert "États-Unis" in m.humanize_for_speech("les USA gagnent")
    assert "contre" in m.humanize_for_speech("Espagne vs Argentine")
    # Les saisons/années ne doivent PAS être touchées
    assert "2025-2026" in m.humanize_for_speech("la saison 2025-2026")
    # Idempotence
    t = m.humanize_for_speech("France 2-1 Brésil")
    assert m.humanize_for_speech(t) == t
    print("    → France 2 à 1 Brésil ✓")


@test("Sous-titres ASS (groupement par phrases + karaoké)")
def test_subtitles_ass():
    import news_video_generator as m
    words = [{"word": w, "start": i*0.3, "end": i*0.3+0.25}
             for i, w in enumerate("À la une, France 2 à 1 Brésil. Une victoire historique.".split())]
    path = m.build_ass(words, "/tmp/test_suite.ass")
    content = open(path).read()
    assert content.count("Dialogue:") == len(words), "1 évènement par mot attendu"
    assert "H18C5F5" in content, "surlignage doré absent"
    assert "fad(120" in content, "fondu d'entrée absent"
    assert "DejaVu Sans" in content
    # timestamps croissants
    import re
    starts = re.findall(r"Dialogue: 0,(\d:\d+:\d+\.\d+)", content)
    assert starts == sorted(starts)
    print(f"    → {len(words)} mots, {content.count('Dialogue:')} évènements ASS")


# ── Audio ──────────────────────────────────────────────────────

@test("espeak-ng — génération WAV")
def test_espeak():
    import news_video_generator as m
    out = "/tmp/test_espeak.wav"
    ok  = m.text_to_wav_espeak("Test de synthèse vocale.", out)
    assert ok, "espeak n'a pas généré le WAV"
    assert os.path.getsize(out) > 5000
    print(f"    → WAV {os.path.getsize(out)//1024}KB")

@test("ffmpeg — WAV → MP3")
def test_wav_mp3():
    import news_video_generator as m
    wav = "/tmp/test_espeak.wav"
    mp3 = "/tmp/test_espeak.mp3"
    if not os.path.exists(wav):
        m.text_to_wav_espeak("Test.", wav)
    ok = m.wav_to_mp3(wav, mp3)
    assert ok
    assert os.path.getsize(mp3) > 1000
    print(f"    → MP3 {os.path.getsize(mp3)//1024}KB")

@test("edge-tts — synthèse fr-FR-DeniseNeural")
def test_edge_tts_audio():
    import news_video_generator as m
    out_wav = "/tmp/test_edge.wav"
    # text_to_wav_edge retourne (succès, word_timings) — bien déballer le
    # tuple, sinon "if not ok" est toujours faux (un tuple est truthy)
    ok, words = m.text_to_wav_edge("Bonjour, ceci est un test de la voix Microsoft Neural.", out_wav)
    if not ok:
        print(f"    {YELLOW}⚠️  edge-tts indisponible (réseau ?), espeak sera utilisé{RESET}")
        return
    assert os.path.exists(out_wav)
    print(f"    → WAV {os.path.getsize(out_wav)//1024}KB")


# ── Pipeline complet ────────────────────────────────────────────

@test("Pipeline complet 5 news (demo, sans API)")
def test_full_pipeline():
    import news_video_generator as m
    output_dir = Path("/tmp/test_output")
    photos_dir = output_dir / "photos"
    audio_dir  = output_dir / "audio"
    for d in [output_dir, photos_dir, audio_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # 1. News
    script_data = m._demo_news(5)
    assert len(script_data["news"]) == 5

    # 2. Photos
    cfg = {**m.CONFIG, "UNSPLASH_KEY": ""}  # forcer fonds locaux
    photo_paths = m.get_photos(script_data, cfg, photos_dir)
    assert len(photo_paths) == 5
    for p in photo_paths:
        assert os.path.exists(p), f"Photo manquante : {p}"

    # 3. Audio
    segments = m.generate_all_audio(script_data, cfg, audio_dir)
    assert len(segments) == 7  # intro + 5 news + outro
    total = sum(s["duration"] for s in segments)
    print(f"    → Audio : {total:.1f}s")

    # 4. Vidéo
    video_path = m.build_video(segments, photo_paths, script_data, cfg, output_dir)
    assert os.path.exists(video_path)
    size_mb = os.path.getsize(video_path) / 1_000_000
    assert size_mb > 0.5
    print(f"    → Vidéo : {video_path} ({size_mb:.1f}MB)")
    return video_path


# ── Main ───────────────────────────────────────────────────────

def main():
    quick = "--quick" in sys.argv

    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════╗
║      🧪 NEWS VIDEO GENERATOR — Test Suite                ║
╚══════════════════════════════════════════════════════════╝{RESET}
""")

    # Tests toujours lancés
    test_import()
    test_deps()
    test_edge_tts()
    test_system_deps()
    test_demo_news()
    test_rss()
    test_background()
    test_render_intro()
    test_render_news()
    test_render_outro()
    test_palette()
    test_metadata()
    test_worldcup_demo()
    test_subtitles_ass()
    test_speech()
    test_espeak()
    test_wav_mp3()
    test_edge_tts_audio()

    # Pipeline complet (lent — skipper avec --quick)
    if not quick:
        test_full_pipeline()

    # ── Résumé ──
    total = len(passed) + len(failed)
    print(f"""
{BOLD}╔══════════════════════════════════════════════════════════╗
║  📊 RÉSULTATS : {len(passed)}/{total} tests passés{RESET}{BOLD}
╚══════════════════════════════════════════════════════════╝{RESET}""")

    for t in passed:
        print(f"  {GREEN}✅ {t}{RESET}")
    for t in failed:
        print(f"  {RED}❌ {t}{RESET}")

    if failed:
        print(f"\n{RED}⚠️  {len(failed)} test(s) échoué(s){RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}🎉 Tous les tests passent !{RESET}")


if __name__ == "__main__":
    main()
