"""
video.py — ÉTAPE 4/5 : Assemblage vidéo (ffmpeg direct), mixage musique,
validation et nettoyage.

C'est le module qui orchestre render.py (frames PNG) et subtitles.py
(filtre karaoke) pour produire le MP4 final via ffmpeg, sans passer par
MoviePy (plus rapide et plus robuste sur un runner CI limité).
"""
import os
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

from PIL import Image

from .config import W, H
from .render import render_intro, render_outro, render_news_frame, _fonts
from .subtitles import generate_subtitle_filter


def get_music_path(output_dir: Path) -> str | None:
    """
    Cherche un fichier musique de fond dans cet ordre :
    1. output/music.mp3 (fichier custom posé par l'utilisateur)
    2. assets/ambient_news.mp3 (bundlé dans le repo)
    Retourne None si aucun fichier trouvé.
    """
    candidates = [
        output_dir / "music.mp3",
        Path("assets") / "ambient_news.mp3",
        Path("ambient_news.mp3"),
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 10_000:
            return str(p)
    return None


def mix_background_music(video_path: str, music_path: str,
                          volume: float, output_path: str) -> bool:
    """
    Mixe une musique de fond sous la piste audio de la vidéo.

    - La musique est mise en boucle pour couvrir toute la durée
    - Volume réduit à `volume` (0.07 ≈ -23dB — inaudible mais présente)
    - Fade out 2s en fin de vidéo
    - La piste voix reste intacte et prioritaire
    """
    # Obtenir la durée de la vidéo
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True
    )
    try:
        total_dur = float(r.stdout.strip())
    except Exception:
        print("  ⚠️  Impossible de lire la durée vidéo — musique ignorée")
        return False

    fadeout_start = max(0, total_dur - 2.0)

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-stream_loop", "-1", "-i", music_path,   # boucle infinie
        "-filter_complex",
        (
            f"[1:a]volume={volume},"               # réduire le volume
            f"afade=t=out:st={fadeout_start:.2f}:d=2.0,"  # fade out final
            f"atrim=duration={total_dur:.2f}[music];"      # couper à la durée exacte
            "[0:a][music]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[aout]"
        ),
        "-map", "0:v",
        "-map", "[aout]",
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        output_path
    ]

    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ⚠️  Mix musique échoué : {r.stderr[-200:]}")
        return False
    return True


def validate_mp4(path: str) -> tuple[bool, str]:
    """
    Vérifie qu'un MP4 est lisible et non corrompu via ffprobe.
    Retourne (ok, message).
    """
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=duration,width,height,codec_name",
        "-of", "json", path
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, f"ffprobe erreur : {r.stderr[:200]}"
    try:
        info = json.loads(r.stdout)
        streams = info.get("streams", [])
        if not streams:
            return False, "Aucun stream vidéo détecté"
        s = streams[0]
        w, h   = s.get("width", 0), s.get("height", 0)
        codec  = s.get("codec_name", "?")
        dur    = float(s.get("duration", 0))
        if dur < 5:
            return False, f"Durée trop courte : {dur:.1f}s"
        if w != W or h != H:
            return False, f"Résolution incorrecte : {w}×{h} (attendu {W}×{H})"
        return True, f"{codec} {w}×{h} {dur:.1f}s {os.path.getsize(path)/1e6:.1f}MB"
    except Exception as e:
        return False, f"Erreur parsing ffprobe : {e}"


def cleanup_frames(frames_dir: Path):
    """Supprime le dossier frames temporaire après encodage."""
    try:
        shutil.rmtree(frames_dir)
        print(f"  🧹 Frames supprimées : {frames_dir}")
    except Exception as e:
        print(f"  ⚠️  Nettoyage frames échoué : {e}")


def build_video(segments: list[dict], photo_paths: list[str],
                script_data: dict, config: dict, output_dir: Path) -> str:
    print("\n🎬 ÉTAPE 4 — Assemblage et encodage de la vidéo...")
    fonts      = _fonts()
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    photo_map  = {i + 1: p for i, p in enumerate(photo_paths)}

    # ── Rendre chaque frame en PNG ──
    segment_files = []
    for idx, seg in enumerate(segments):
        stype = seg["type"]
        dur   = seg.get("duration", 6.0) + 0.3

        if stype == "intro":
            frame = render_intro(seg["text"], fonts)
        elif stype == "outro":
            frame = render_outro(seg["text"], fonts)
        else:
            photo_p = photo_map.get(seg["index"], list(photo_map.values())[0])
            frame   = render_news_frame(seg, photo_p, fonts)

        frame_path = str(frames_dir / f"frame_{idx:02d}.png")
        Image.fromarray(frame).save(frame_path)

        segment_files.append({
            "frame":    frame_path,
            "audio":    seg.get("audio"),
            "duration": dur,
            "label":    seg.get("titre", stype)[:40],
            "type":     stype,
            "words":    seg.get("words", []),
        })
        print(f"  🖼️  [{stype:5}] {segment_files[-1]['label']:<42} {dur:.1f}s")

    # ── Encoder chaque segment en clip MP4 ──
    print("\n  ⚙️  Encodage MP4 via ffmpeg...")
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M")
    out_path   = str(output_dir / f"journal_{timestamp}.mp4")
    clip_paths = []

    # Fondu noir : 0.3s en entrée ET sortie de chaque clip
    FADE_D = 0.3

    for i, seg in enumerate(segment_files):
        clip_out = str(frames_dir / f"clip_{i:02d}.mp4")
        dur      = seg["duration"]
        fps      = config["FPS"]

        # ── Filtre vidéo : scale + Ken Burns + fade + sous-titres animés ──
        sub_filter = ""
        words = seg.get("words", [])
        if words and dur > 1:
            sub_filter = generate_subtitle_filter(words, W, H)

        vf_parts = [f"scale={W}:{H}"]

        # Ken Burns (zoom lent) uniquement sur les news, pas intro/outro
        # (qui sont des cartes/logos, pas des photos) : casse l'effet figé
        # d'une image statique pendant 10-15s, donne l'impression de
        # plusieurs plans sans avoir besoin de plusieurs photos.
        # Alterné zoom in / zoom out selon l'index pour varier le rythme.
        if seg.get("type") == "news" and dur > 1.5:
            n_frames  = max(1, int(dur * fps))
            zoom_rate = min(0.10, 0.9 / n_frames)   # zoom total borné à ~+10%
            if i % 2 == 0:
                # Zoom in : part de 1.0, grossit doucement
                zoom_expr = f"zoompan=z='min(zoom+{zoom_rate:.5f},1.10)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps}"
            else:
                # Zoom out : part déjà zoomé, revient doucement vers 1.0
                zoom_expr = f"zoompan=z='if(eq(on,0),1.10,max(zoom-{zoom_rate:.5f},1.0))':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={W}x{H}:fps={fps}"
            vf_parts.append(zoom_expr)

        vf_parts += [
            f"fade=t=in:st=0:d={FADE_D}:color=black",
            f"fade=t=out:st={max(0, dur - FADE_D):.2f}:d={FADE_D}:color=black",
        ]
        if sub_filter:
            vf_parts.append(sub_filter)
        vf = ",".join(vf_parts)

        if seg["audio"] and os.path.exists(seg["audio"]):
            # Filtre audio : fade in + fade out (évite les clics)
            af = (
                f"afade=t=in:st=0:d={FADE_D},"
                f"afade=t=out:st={max(0, dur - FADE_D):.2f}:d={FADE_D}"
            )
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", seg["frame"],
                "-i", seg["audio"],
                "-c:v", "libx264", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-crf", "19", "-maxrate", "8M", "-bufsize", "12M",
                "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
                "-vf", vf,
                "-af", af,
                "-shortest",
                "-r", str(config["FPS"]),
                clip_out
            ]
        else:
            cmd = [
                "ffmpeg", "-y",
                "-loop", "1", "-i", seg["frame"],
                "-t", str(dur),
                "-c:v", "libx264", "-preset", "fast",
                "-pix_fmt", "yuv420p",
                "-crf", "19", "-maxrate", "8M", "-bufsize", "12M",
                "-vf", vf,
                "-r", str(config["FPS"]),
                clip_out
            ]

        r = subprocess.run(cmd, capture_output=True, text=True)
        clip_ok = r.returncode == 0 and os.path.exists(clip_out)

        # Vérifier que le clip a bien une piste vidéo (pas juste audio)
        if clip_ok:
            probe = subprocess.run(
                ["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", clip_out],
                capture_output=True, text=True
            )
            if "video" not in probe.stdout:
                clip_ok = False
                print(f"  ⚠️  Clip {i} sans piste vidéo — retry sans sous-titres")
                # Retry sans le filtre sous-titres (cause la plus probable)
                vf_retry = ",".join(vf_parts[:3])  # scale + fades, sans drawtext
                cmd_retry = [a if a != vf else vf_retry for a in cmd]
                r2 = subprocess.run(cmd_retry, capture_output=True, text=True)
                if r2.returncode == 0 and os.path.exists(clip_out):
                    probe2 = subprocess.run(
                        ["ffprobe", "-v", "error", "-select_streams", "v:0",
                         "-show_entries", "stream=codec_type", "-of", "csv=p=0", clip_out],
                        capture_output=True, text=True
                    )
                    clip_ok = "video" in probe2.stdout

        if clip_ok:
            clip_paths.append(clip_out)
            print(f"  ✂️   Clip {i:02d} OK  ({dur:.1f}s + fondu {FADE_D}s)")
        else:
            print(f"  ⚠️  Clip {i} échoué : {r.stderr[-150:]}")

    if not clip_paths:
        raise RuntimeError("Aucun clip généré — pipeline interrompu")

    # ── Concaténation finale ──
    # Chemins ABSOLUS dans concat.txt : ffmpeg résout les chemins relatifs
    # par rapport au dossier du fichier concat.txt, pas au cwd — donc on
    # utilise os.path.abspath pour éviter tout problème de double-préfixe.
    concat_file = str(frames_dir / "concat.txt")
    with open(concat_file, "w") as f:
        for cp in clip_paths:
            abs_cp = os.path.abspath(cp)
            f.write(f"file '{abs_cp}'\n")

    cmd_final = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_file,
        "-c:v", "libx264", "-preset", "medium",
        "-pix_fmt", "yuv420p",
        "-crf", "20", "-maxrate", "8M", "-bufsize", "12M",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-r", str(config["FPS"]),
        "-movflags", "+faststart",
        out_path
    ]
    r = subprocess.run(cmd_final, capture_output=True, text=True)

    if r.returncode != 0:
        cleanup_frames(frames_dir)
        raise RuntimeError(f"Concaténation ffmpeg échouée : {r.stderr[-300:]}")

    # ── Validation MP4 ──
    ok, msg = validate_mp4(out_path)
    if ok:
        print(f"  ✅ Vidéo validée : {msg}")
    else:
        cleanup_frames(frames_dir)
        raise RuntimeError(f"MP4 corrompu : {msg}")

    # ── Nettoyage frames temporaires ──
    cleanup_frames(frames_dir)

    return out_path
