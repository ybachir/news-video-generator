# 📰 News Video Generator

> Génère automatiquement un journal vidéo **9:16** quotidien prêt pour Reels / TikTok / Shorts.

**Pipeline complet :**
```
Scraping actualités → Script IA (Claude) → Photos (Unsplash) → Voix (Kokoro TTS) → Vidéo MP4
```

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![TTS](https://img.shields.io/badge/TTS-Kokoro%2082M-purple)
![Format](https://img.shields.io/badge/Format-9:16%20Vertical-orange)

---

## 🚀 Installation rapide

```bash
# 1. Cloner le repo
git clone https://github.com/ybachir/news-video-generator.git
cd news-video-generator

# 2. Installer les dépendances Python
pip install -r requirements.txt

# 3. Installer les dépendances système
sudo apt install espeak-ng ffmpeg        # Linux / Ubuntu
brew install espeak ffmpeg               # macOS

# 4. Configurer les clés API
cp .env.example .env
# Édite .env avec tes clés

# 5. Lancer !
python3 news_video_generator.py
```

---

## ⚙️ Configuration

Copie `.env.example` en `.env` et remplis tes clés :

| Variable | Requis | Source | Usage |
|----------|--------|--------|-------|
| `ANTHROPIC_KEY` | ✅ Recommandé | [console.anthropic.com](https://console.anthropic.com) | Scraping news + script IA |
| `UNSPLASH_KEY` | Optionnel | [unsplash.com/developers](https://unsplash.com/developers) | Photos HD (50 req/h gratuit) |
| `NEWSAPI_KEY` | Optionnel | [newsapi.org](https://newsapi.org) | Backup news (100 req/jour gratuit) |

Sans aucune clé → mode **démo** avec 10 news simulées.

---

## 🎬 Ce que ça génère

```
output/
├── journal_20260605_1000.mp4     ← Vidéo finale 9:16 (1080×1920)
├── script_20260605_1000.json     ← Script JSON réutilisable
├── photos/
│   ├── news_01.jpg
│   └── ...
└── audio/
    ├── intro.mp3
    ├── news_01.mp3
    └── ...
```

**Exemple de sortie vidéo :**
- Durée : ~8-12 minutes pour 10 news
- Résolution : 1080×1920 (Full HD vertical)
- Format : MP4 H.264 / AAC

---

## 🎙️ Moteur TTS — Kokoro

Ce projet utilise **[Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M)**, le meilleur TTS open-source gratuit :

- 🆓 100% gratuit, Apache 2.0 (commercial OK)
- 🇫🇷 Voix française native : `ff_siwis`
- 📴 100% offline après le 1er téléchargement (~85MB)
- 🏆 Qualité supérieure à Google WaveNet selon les benchmarks

```bash
# Test de voix standalone
python3 tts_kokoro.py "Bonjour, ceci est un test." test.mp3
```

**Fallback automatique :** si Kokoro échoue → `espeak-ng` prend le relais.

---

## 📋 Pipeline détaillé

### Étape 1 — Actualités
- **Mode A** : Claude + WebSearch → vraies news du jour en temps réel
- **Mode B** : RSS feeds (Le Monde, France24, BBC, Al Jazeera, Reuters…)
- **Mode C** : 10 news de démo (sans aucune clé)

### Étape 2 — Photos
- **Mode A** : Unsplash API (photos HD, libres de droits)
- **Mode B** : Fonds visuels stylés générés localement par catégorie

### Étape 3 — Audio
- Kokoro TTS (`ff_siwis`) → voix naturelle française
- Fallback : espeak-ng

### Étape 4 — Vidéo
- Assemblage avec MoviePy
- Overlay texte, numéros, source, catégorie
- Export MP4 H.264 vertical 9:16

---

## 🗺️ Roadmap

- [ ] 🎵 Musique de fond (jingle + ambiance)
- [ ] 📝 Sous-titres animés (karaoke style)
- [ ] 🎞️ Transitions entre les slides
- [ ] 🗣️ Migration ElevenLabs (voix premium)
- [ ] 📲 Publication automatique Instagram / TikTok
- [ ] ⏰ Cron job — journal généré chaque matin à 7h
- [ ] 🌍 Support multilingue (EN, ES, DE…)

---

## 📦 Dépendances

| Package | Usage |
|---------|-------|
| `moviepy` | Assemblage vidéo |
| `kokoro` | TTS voix naturelle |
| `soundfile` | Export audio WAV |
| `Pillow` | Génération des frames |
| `requests` | APIs (Anthropic, Unsplash) |
| `feedparser` | RSS feeds |
| `numpy` | Traitement audio/image |
| `ffmpeg` (système) | Encodage MP3/MP4 |
| `espeak-ng` (système) | TTS fallback |

---

## 📄 Licence

**Tous droits réservés © ybachir** — Ce projet est privé, aucune utilisation, copie ou distribution n'est autorisée sans permission explicite de l'auteur.

---

*Généré avec ❤️ par Claude (Anthropic)*
