# 📰 News Video Generator

> Génère automatiquement un journal vidéo **9:16** quotidien prêt pour Reels / TikTok / Shorts.  
> **100% gratuit** — aucune clé payante requise.

**Pipeline :**
```
RSS feeds → Groq (Llama 3.3, gratuit) → Photos (Unsplash) → edge-tts (Microsoft Neural) → ffmpeg → MP4
```

![Python](https://img.shields.io/badge/Python-3.10+-blue)
![TTS](https://img.shields.io/badge/TTS-edge--tts%20Neural-purple)
![Format](https://img.shields.io/badge/Format-9:16%20Vertical-orange)
![Cost](https://img.shields.io/badge/Coût-100%25%20Gratuit-brightgreen)

---

## 🎬 Template vidéo

Style **premium sombre/doré** — optimisé pour le taux de clic sur Reels/TikTok/Shorts.

| Élément | Choix |
|---------|-------|
| Fond | `#0A0A12` (noir bleuté) |
| Accent | `#F5C518` (or vif) |
| Texte | Blanc / Gris clair |
| Format | 1080×1920 (9:16) |
| Durée | ~3 min (5 news) |
| Structure | Intro → 5 News → Outro |

---

## 🚀 Installation rapide

```bash
# 1. Cloner le repo
git clone https://github.com/ybachir/news-video-generator.git
cd news-video-generator

# 2. Dépendances Python
pip install -r requirements.txt

# 3. Dépendances système
sudo apt install ffmpeg          # Linux / Ubuntu
brew install ffmpeg              # macOS

# 4. Configurer les clés
cp .env.example .env
# Édite .env avec tes clés

# 5. Lancer !
python3 news_video_generator.py
```

---

## ⚙️ Configuration

| Variable | Requis | Source | Usage |
|----------|--------|--------|-------|
| `GROQ_API_KEY` | ✅ Recommandé | [console.groq.com](https://console.groq.com) | Structuration IA des news (Llama 3.3) — 14 400 req/jour gratuit |
| `UNSPLASH_KEY` | Optionnel | [unsplash.com/developers](https://unsplash.com/developers) | Photos HD (50 req/h gratuit) |

Sans aucune clé → mode **démo** avec 5 news simulées et fonds générés localement.

---

## 🏗️ Pipeline détaillé

### Étape 1 — Collecte & structuration des actualités
- Scraping de **10 RSS feeds** (Le Monde, France24, BBC, Reuters, Al Jazeera…)
- Sélection et réécriture style journaliste TV via **Groq (Llama 3.3-70B, gratuit)**
- Fallback : RSS brut si Groq indisponible
- Fallback ultime : 5 news de démo

### Étape 2 — Visuels
- **Unsplash API** (photos HD libres de droits, 50 req/h gratuit)
- Fallback : fonds premium générés localement par catégorie (dégradé sombre + halos)

### Étape 3 — Synthèse vocale
- **edge-tts** (`fr-FR-DeniseNeural`) — voix Microsoft Neural, gratuit, non officiel
- Fallback : `espeak-ng` (voix robotique, 100% local)

### Étape 4 — Assemblage vidéo
- Rendu des frames PNG via **Pillow**
- Encodage H.264 et assemblage via **ffmpeg direct** (3× plus rapide que MoviePy)
- Export MP4 optimisé pour mobile (`+faststart`)

---

## 📦 Dépendances

| Package | Usage |
|---------|-------|
| `moviepy` | Lecture durée audio |
| `Pillow` | Rendu des frames |
| `numpy` | Traitement image |
| `feedparser` | Scraping RSS |
| `requests` | APIs (Groq, Unsplash) |
| `edge-tts` | TTS Microsoft Neural (gratuit) |
| `ffmpeg` (système) | Encodage MP3/MP4 |

---

## 🗺️ Roadmap

- [x] ✅ Collecte news via RSS + Groq (Llama 3.3 gratuit)
- [x] ✅ Template vidéo premium sombre/doré
- [x] ✅ TTS edge-tts (Microsoft Neural) + retry x3 + timeout
- [x] ✅ Encodage ffmpeg direct (rapide)
- [x] ✅ Validation MP4 (ffprobe) + nettoyage automatique
- [x] ✅ Transitions fondu noir 0.3s entre les segments
- [x] ✅ Sous-titres animés mot par mot (ffmpeg drawtext)
- [x] ✅ Musique de fond ambient (mix -23dB, boucle, fade out)
- [x] ✅ GitHub Actions workflow (cron 7h UTC, publication automatique)
- [x] ✅ Publication YouTube (Data API v3)
- [x] ✅ Publication Instagram Reels (Meta Graph API)
- [ ] 🌍 Support multilingue (EN, ES, AR…)
- [ ] 📊 Dashboard stats (vues, likes par vidéo)

---

## 📤 Publication automatique

### YouTube
```bash
# 1. Installer les dépendances
pip install google-api-python-client google-auth-oauthlib

# 2. Télécharger client_secrets.json depuis Google Cloud Console
#    (YouTube Data API v3 → Credentials → OAuth 2.0 → Desktop App)

# 3. Générer le token (une seule fois en local)
python3 generate_youtube_token.py

# 4. Ajouter dans GitHub Secrets :
#    YOUTUBE_TOKEN_JSON  → contenu de youtube_token_b64.txt
#    YOUTUBE_CLIENT_JSON → contenu de client_secrets_b64.txt
```

### Instagram Reels
```bash
# Prérequis : compte Instagram Business ou Créateur
# 1. Créer une app sur developers.facebook.com
# 2. Obtenir les permissions instagram_content_publish
# 3. Générer un token longue durée (60 jours)

# Ajouter dans GitHub Secrets :
#    INSTAGRAM_USER_ID → ID numérique du compte
#    INSTAGRAM_TOKEN   → access token longue durée
#    VIDEO_PUBLIC_URL  → URL publique du MP4 (requis par Meta)
```

### Publication manuelle
```bash
python3 publish.py --video output/journal_xxx.mp4 --platform youtube
python3 publish.py --video output/journal_xxx.mp4 --platform instagram
python3 publish.py --video output/journal_xxx.mp4 --platform all
```

---

## 📄 Licence

**Tous droits réservés © ybachir**

---

*Généré avec ❤️ par Claude (Anthropic)*

