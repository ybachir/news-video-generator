#!/usr/bin/env python3
"""
run_pipeline.py — Script de génération appelé par GitHub Actions
Remplace le python3 -c inline dans le workflow (plus lisible, plus fiable)

Usage:
    python3 run_pipeline.py              # mode full
    python3 run_pipeline.py --demo       # mode demo (sans API)
"""
import sys, os, argparse
sys.path.insert(0, '.')

from pathlib import Path
import news_video_generator as m

parser = argparse.ArgumentParser()
parser.add_argument("--demo", action="store_true", help="Mode demo sans API")
args = parser.parse_args()

# Mode demo : désactiver les APIs
if args.demo:
    m.CONFIG['GROQ_API_KEY'] = ''
    m.CONFIG['UNSPLASH_KEY'] = ''
    print("▶ Mode DEMO — news simulées, fonds locaux")
else:
    # Injecter les clés depuis l'environnement
    m.CONFIG['GROQ_API_KEY'] = os.getenv('GROQ_API_KEY', '')
    m.CONFIG['UNSPLASH_KEY'] = os.getenv('UNSPLASH_KEY', '')
    print("▶ Mode FULL — RSS + Groq + Unsplash")

output_dir = Path('output')
photos_dir = output_dir / 'photos'
audio_dir  = output_dir / 'audio'
for d in [output_dir, photos_dir, audio_dir]:
    d.mkdir(parents=True, exist_ok=True)

script_data = m.get_news(m.CONFIG)
photo_paths = m.get_photos(script_data, m.CONFIG, photos_dir)
segments    = m.generate_all_audio(script_data, m.CONFIG, audio_dir)
video_path  = m.build_video(segments, photo_paths, script_data, m.CONFIG, output_dir)

size = os.path.getsize(video_path) / 1_000_000
print(f'✅ Vidéo générée : {video_path} ({size:.1f}MB)')
