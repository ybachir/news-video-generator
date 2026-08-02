#!/usr/bin/env python3
"""
run_pipeline.py — Script de génération appelé par GitHub Actions

Usage:
    python3 run_pipeline.py              # mode full
    python3 run_pipeline.py --demo       # mode demo (sans API)
    python3 run_pipeline.py --top-n 7    # nombre de news (défaut 5)

Étapes : News → Photos → Voix → Vidéo → Musique de fond → metadata.json

NOTE : ce script exécute le MÊME pipeline complet que
`python3 -m news_video_generator`, y compris le mixage de la musique de
fond et l'écriture des métadonnées de publication. (Une version
précédente dupliquait les étapes et OUBLIAIT la musique : les vidéos
produites par le cron sortaient muettes en fond sonore.)
"""
import sys, os, argparse
sys.path.insert(0, '.')

from pathlib import Path
import news_video_generator as m

parser = argparse.ArgumentParser()
parser.add_argument("--demo", action="store_true", help="Mode demo sans API")
parser.add_argument("--top-n", type=int, default=None, help="Nombre de news (défaut: 5)")
parser.add_argument("--theme", default="journal",
                    choices=["journal", "worldcup", "france", "deepdive", "weekly"],
                    help="journal = actu générale | worldcup = Spécial Coupe du Monde 2026 | "
                         "france = Spécial actu France | deepdive = Zoom Sur (1 vidéo détaillée par sujet dominant) | "
                         "weekly = Récap hebdo France (vidéo longue 16:9, pas un Short)")
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

m.CONFIG['THEME'] = args.theme
if args.theme == "worldcup":
    print("▶ Édition SPÉCIAL COUPE DU MONDE 2026 ⚽")
elif args.theme == "france":
    print("▶ Édition SPÉCIAL FRANCE 🇫🇷")
elif args.theme == "deepdive":
    print("▶ Édition ZOOM SUR 🔎 (une vidéo détaillée par sujet dominant du jour)")
elif args.theme == "weekly":
    print("▶ Édition RÉCAP HEBDO 📅 (vidéo longue 16:9, pas un Short)")

if args.top_n:
    m.CONFIG['TOP_N'] = max(3, min(args.top_n, 10))

# main() exécute TOUT le pipeline : news, photos, audio, vidéo,
# mixage musique, validation, métadonnées — une seule source de vérité.
# En mode 'deepdive', main() retourne une LISTE de chemins (une vidéo
# par sujet) au lieu d'un chemin unique.
result = m.main()

if isinstance(result, list):
    total_mb = sum(os.path.getsize(p) for p in result) / 1_000_000
    print(f'✅ {len(result)} vidéos générées ({total_mb:.1f}MB au total) :')
    for p in result:
        print(f'   - {p} ({os.path.getsize(p) / 1_000_000:.1f}MB)')
else:
    size = os.path.getsize(result) / 1_000_000
    print(f'✅ Vidéo générée : {result} ({size:.1f}MB)')
