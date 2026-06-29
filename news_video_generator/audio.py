"""
audio.py — ÉTAPE 3 : Synthèse vocale (edge-tts → espeak fallback).

edge-tts (Microsoft Neural, gratuit) capture le timing réel mot par mot via
les événements WordBoundary, nécessaire pour les sous-titres animés. En cas
d'échec, on retombe sur espeak-ng avec une estimation de timing par poids
de longueur de mot.
"""
import os
import re
import time
import asyncio
import subprocess
from pathlib import Path

EDGE_TTS_VOICE    = "fr-FR-DeniseNeural"
EDGE_TTS_RATE     = "+8%"
EDGE_TTS_RETRIES  = 3
EDGE_TTS_TIMEOUT  = 20   # secondes par tentative


def text_to_wav_edge(text: str, wav_path: str) -> tuple[bool, list[dict]]:
    """
    Synthèse vocale via edge-tts (Microsoft Neural — gratuit, non officiel).
    Voix    : fr-FR-DeniseNeural
    Retries : 3 tentatives avec backoff exponentiel
    Timeout : 20s par tentative (évite les hangs sur GitHub Actions)

    Retourne (succès, word_timings) où word_timings est une liste de
    {"word": str, "start": float, "end": float} en secondes, capturée
    via les événements WordBoundary du flux edge-tts (nécessaire pour
    les sous-titres animés mot par mot).
    """
    try:
        import edge_tts
    except ImportError:
        return False, []

    mp3_tmp = wav_path.replace(".wav", "_edge.mp3")

    async def _fetch():
        communicate = edge_tts.Communicate(
            text, voice=EDGE_TTS_VOICE, rate=EDGE_TTS_RATE
        )
        words = []
        with open(mp3_tmp, "wb") as f:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    # offset/duration sont en unités de 100ns (ticks) côté edge-tts
                    start = chunk["offset"] / 1e7
                    dur   = chunk["duration"] / 1e7
                    words.append({
                        "word":  chunk["text"],
                        "start": start,
                        "end":   start + dur,
                    })
        return words

    for attempt in range(1, EDGE_TTS_RETRIES + 1):
        try:
            words = asyncio.run(
                asyncio.wait_for(_fetch(), timeout=EDGE_TTS_TIMEOUT)
            )
            if not os.path.exists(mp3_tmp) or os.path.getsize(mp3_tmp) < 1000:
                raise ValueError("Fichier MP3 vide ou absent")

            # MP3 → WAV
            r = subprocess.run(
                ["ffmpeg", "-y", "-i", mp3_tmp, wav_path],
                capture_output=True
            )
            try:
                os.remove(mp3_tmp)
            except Exception:
                pass

            if r.returncode == 0 and os.path.exists(wav_path):
                return True, words
            raise ValueError(f"ffmpeg conversion échouée : {r.stderr[-100:]}")

        except asyncio.TimeoutError:
            print(f"  ⚠️  edge-tts timeout (tentative {attempt}/{EDGE_TTS_RETRIES})")
        except Exception as e:
            print(f"  ⚠️  edge-tts erreur (tentative {attempt}/{EDGE_TTS_RETRIES}) : {e}")

        if attempt < EDGE_TTS_RETRIES:
            time.sleep(2 ** attempt)   # backoff : 2s, 4s

    # Nettoyage si le MP3 temporaire traîne
    try:
        if os.path.exists(mp3_tmp):
            os.remove(mp3_tmp)
    except Exception:
        pass

    return False, []


def text_to_wav_espeak(text: str, wav_path: str) -> bool:
    """Fallback espeak-ng."""
    text_clean = re.sub(r'[^\w\s\.,;:!?\-\'\u00C0-\u024F]', ' ', text)
    cmd = ["espeak-ng", "-v", "fr", "-s", "155", "-p", "52",
           "-a", "180", "-g", "8", "-w", wav_path, text_clean]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(wav_path)


def wav_to_mp3(wav_path: str, mp3_path: str) -> bool:
    cmd = ["ffmpeg", "-y", "-i", wav_path, "-ar", "44100", "-ab", "128k", mp3_path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0 and os.path.exists(mp3_path)


def _estimate_word_timings(text: str, total_duration: float) -> list[dict]:
    """
    Fallback quand on n'a pas de timing réel (espeak, ou edge-tts sans
    WordBoundary) : répartit les mots uniformément sur la durée totale,
    pondéré par la longueur de chaque mot (approximation raisonnable).
    """
    words = text.split()
    if not words:
        return []
    weights = [max(len(w), 2) for w in words]
    total_w = sum(weights)
    timings = []
    t = 0.0
    for w, wt in zip(words, weights):
        dur = total_duration * (wt / total_w)
        timings.append({"word": w, "start": t, "end": t + dur})
        t += dur
    return timings


def make_audio(text: str, name: str, audio_dir: Path) -> tuple[str | None, float, str, list[dict]]:
    wav = str(audio_dir / f"{name}.wav")
    mp3 = str(audio_dir / f"{name}.mp3")

    # Essai edge-tts (fournit le timing réel mot par mot)
    ok, word_timings = text_to_wav_edge(text, wav)
    engine = "edge-tts"

    # Fallback espeak (pas de timing réel -> estimation)
    if not ok:
        ok = text_to_wav_espeak(text, wav)
        engine = "espeak-ng (fallback)"
        word_timings = []

    if not ok:
        return None, 5.0, "échec", []

    if not wav_to_mp3(wav, mp3):
        return None, 5.0, "échec", []

    try:
        os.remove(wav)
    except Exception:
        pass

    try:
        from moviepy import AudioFileClip
        clip = AudioFileClip(mp3)
        dur  = clip.duration
        clip.close()
    except Exception:
        dur = len(text.split()) / 2.5

    if not word_timings:
        word_timings = _estimate_word_timings(text, dur)

    return mp3, dur, engine, word_timings


def generate_all_audio(script_data: dict, config: dict, audio_dir: Path) -> list[dict]:
    print("\n🎙️  ÉTAPE 3 — Synthèse vocale (edge-tts / espeak fallback)...")
    audio_dir.mkdir(exist_ok=True)
    segments = []
    engines_used = []

    # Intro
    intro_text = script_data.get("intro", "Bonjour, voici les actualités du jour.")
    mp3, dur, engine, words = make_audio(intro_text, "intro", audio_dir)
    engines_used.append(engine)
    segments.append({"type": "intro", "audio": mp3, "duration": dur,
                     "text": intro_text, "titre": "Journal du Monde", "words": words})
    print(f"  ✅ Intro : {dur:.1f}s — moteur : {engine}")

    # News
    for i, item in enumerate(script_data["news"]):
        n    = i + 1
        text = f"Numéro {n}. {item['titre']}. {item['resume']}"
        mp3, dur, engine, words = make_audio(text, f"news_{n:02d}", audio_dir)
        engines_used.append(engine)
        segments.append({
            "type":      "news",
            "index":     n,
            "audio":     mp3,
            "duration":  dur,
            "text":      item["resume"],
            "spoken_text": text,    # texte réellement prononcé (pour aligner les sous-titres)
            "words":     words,     # timing mot par mot (start/end en secondes)
            "titre":     item["titre"],
            "source":    item.get("source", ""),
            "categorie": item.get("categorie", "monde"),
            "keywords":  item.get("keywords_photo", []),
        })
        print(f"  🎙️  #{n:2} {dur:.1f}s — moteur : {engine} — {item['titre'][:45]}")

    # Outro
    outro_text = script_data.get("outro", "Merci et à bientôt.")
    mp3, dur, engine, words = make_audio(outro_text, "outro", audio_dir)
    engines_used.append(engine)
    segments.append({"type": "outro", "audio": mp3, "duration": dur,
                     "text": outro_text, "titre": "Merci", "words": words})
    print(f"  ✅ Outro : {dur:.1f}s — moteur : {engine}")

    n_espeak = sum(1 for e in engines_used if "espeak" in e)
    if n_espeak > 0:
        print(f"  ⚠️  ATTENTION : {n_espeak}/{len(engines_used)} segments en fallback espeak-ng "
              f"(voix robotique, pauses marquées) — edge-tts a échoué sur ces segments")

    total = sum(s["duration"] for s in segments)
    print(f"  📊 Durée totale : {total:.0f}s ({total/60:.1f} min)")
    return segments
