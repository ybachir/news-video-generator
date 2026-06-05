#!/usr/bin/env python3
"""
Module TTS Kokoro — remplace espeak dans news_video_generator.py
Voix française naturelle, 100% gratuit, open-source (Apache 2.0)

Installation :
    pip install kokoro soundfile
    sudo apt install espeak-ng   # requis par Kokoro pour le français
    # Le modèle (~85MB) se télécharge automatiquement au premier lancement

Usage standalone :
    python3 tts_kokoro.py "Bonjour, ceci est un test." output.mp3
"""

import os, sys, subprocess, numpy as np
from pathlib import Path

# ── Vérification des dépendances ──
try:
    from kokoro import KPipeline
    import soundfile as sf
    KOKORO_AVAILABLE = True
except ImportError:
    KOKORO_AVAILABLE = False
    print("⚠️  Kokoro non installé. Fallback espeak actif.")
    print("   Pour installer : pip install kokoro soundfile")


# ── Config voix ──
KOKORO_VOICE   = "ff_siwis"   # Seule voix FR native de Kokoro (très bonne qualité)
KOKORO_SPEED   = 1.08          # Légèrement plus rapide pour un rendu journalistique
KOKORO_LANG    = "f"           # f = French
SAMPLE_RATE    = 24000

# Voix alternatives EN si tu veux tester (meilleure qualité que FR pour l'instant) :
# "af_heart", "af_bella", "af_nicole", "am_adam", "am_michael", "bf_emma"


_pipeline = None   # Singleton — chargé une seule fois


def _get_pipeline():
    """Charge le pipeline Kokoro (une seule fois, ~2-3s)."""
    global _pipeline
    if _pipeline is None:
        print("  🔄 Chargement du modèle Kokoro (première fois ~3s)...")
        _pipeline = KPipeline(lang_code=KOKORO_LANG, repo_id='hexgrad/Kokoro-82M')
        print("  ✅ Modèle Kokoro chargé")
    return _pipeline


def kokoro_to_wav(text: str, wav_path: str) -> bool:
    """Génère un fichier WAV depuis du texte via Kokoro."""
    if not KOKORO_AVAILABLE:
        return False
    try:
        pipeline = _get_pipeline()
        chunks = []
        for _, _, audio in pipeline(text, voice=KOKORO_VOICE, speed=KOKORO_SPEED):
            chunks.append(audio)
        if not chunks:
            return False
        audio_full = np.concatenate(chunks)
        sf.write(wav_path, audio_full, SAMPLE_RATE)
        return os.path.exists(wav_path) and os.path.getsize(wav_path) > 0
    except Exception as e:
        print(f"  ⚠️  Kokoro erreur : {e}")
        return False


def espeak_to_wav(text: str, wav_path: str,
                  voice="fr", speed=155, pitch=52) -> bool:
    """Fallback espeak-ng."""
    import re
    text = re.sub(r'[^\w\s\.,;:!?\-\'\u00C0-\u024F]', ' ', text)
    cmd = ["espeak-ng", "-v", voice, "-s", str(speed),
           "-p", str(pitch), "-a", "180", "-g", "8", "-w", wav_path, text]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(wav_path)


def wav_to_mp3(wav_path: str, mp3_path: str) -> bool:
    """Convertit WAV → MP3 avec ffmpeg."""
    cmd = ["ffmpeg", "-y", "-i", wav_path,
           "-ar", "44100", "-ab", "128k", mp3_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(mp3_path)


def text_to_mp3(text: str, mp3_path: str,
                tmp_dir: str = "/tmp") -> tuple[str | None, float]:
    """
    Convertit du texte en MP3.
    Essaie Kokoro d'abord, fallback espeak si échec.
    Retourne (chemin_mp3, durée_secondes).
    """
    wav_path = os.path.join(tmp_dir, Path(mp3_path).stem + "_tmp.wav")

    # Essai Kokoro
    engine = "kokoro"
    ok = kokoro_to_wav(text, wav_path)

    # Fallback espeak
    if not ok:
        engine = "espeak"
        ok = espeak_to_wav(text, wav_path)

    if not ok:
        return None, 5.0

    # WAV → MP3
    if not wav_to_mp3(wav_path, mp3_path):
        return None, 5.0

    # Cleanup WAV
    try:
        os.remove(wav_path)
    except Exception:
        pass

    # Mesurer durée
    try:
        from moviepy import AudioFileClip
        clip = AudioFileClip(mp3_path)
        dur  = clip.duration
        clip.close()
    except Exception:
        # Estimation approximative : ~150 mots/min
        dur = len(text.split()) / 2.5

    return mp3_path, dur


# ── Remplacement drop-in pour news_video_generator.py ──
def generate_all_audio_kokoro(script_data: dict, config: dict,
                               audio_dir: Path) -> list[dict]:
    """
    Remplace generate_all_audio() dans news_video_generator.py.
    Même interface, utilise Kokoro au lieu de espeak.
    """
    print("\n🎙️  ÉTAPE 3 — Synthèse vocale (Kokoro TTS — voix naturelle)...")
    audio_dir.mkdir(exist_ok=True)
    segments = []

    def make(text: str, name: str) -> tuple[str | None, float]:
        mp3 = str(audio_dir / f"{name}.mp3")
        return text_to_mp3(text, mp3, tmp_dir=str(audio_dir))

    # Intro
    intro_text = script_data.get("intro", "Bonjour, voici les actualités.")
    mp3, dur = make(intro_text, "intro")
    segments.append({"type": "intro", "audio": mp3, "duration": dur,
                      "text": intro_text, "titre": "Journal du Monde"})
    print(f"  ✅ Intro : {dur:.1f}s")

    # News
    for i, item in enumerate(script_data["news"]):
        n    = i + 1
        text = f"Numéro {n}. {item['titre']}. {item['resume']}"
        mp3, dur = make(text, f"news_{n:02d}")
        segments.append({
            "type": "news", "index": n,
            "audio": mp3, "duration": dur,
            "text": item["resume"], "titre": item["titre"],
            "source": item.get("source", ""),
            "categorie": item.get("categorie", "monde"),
            "keywords": item.get("keywords_photo", []),
        })
        print(f"  🎙️  #{n:2} {dur:.1f}s — {item['titre'][:55]}...")

    # Outro
    outro_text = script_data.get("outro", "Merci et à bientôt.")
    mp3, dur = make(outro_text, "outro")
    segments.append({"type": "outro", "audio": mp3, "duration": dur,
                      "text": outro_text, "titre": "Merci"})
    print(f"  ✅ Outro : {dur:.1f}s")

    total = sum(s["duration"] for s in segments)
    print(f"  📊 Durée totale : {total:.0f}s ({total/60:.1f} min)")
    return segments


# ── CLI standalone ──
if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage : python3 tts_kokoro.py \"Texte à lire\" output.mp3")
        sys.exit(1)
    text     = sys.argv[1]
    out_path = sys.argv[2]
    print(f"🎙️  Génération : {out_path}")
    mp3, dur = text_to_mp3(text, out_path)
    if mp3:
        print(f"✅ Fichier créé : {mp3} ({dur:.1f}s)")
    else:
        print("❌ Échec de la génération")
        sys.exit(1)
