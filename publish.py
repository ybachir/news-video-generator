#!/usr/bin/env python3
"""
publish.py — Publication automatique du journal vidéo

Plateformes supportées :
  - YouTube  (YouTube Data API v3 — officiel, gratuit 10k unités/jour)
  - Instagram Reels (Meta Graph API — nécessite compte Business/Créateur)

Usage :
    python3 publish.py --video output/journal_xxx.mp4
    python3 publish.py --video output/journal_xxx.mp4 --platform youtube
    python3 publish.py --video output/journal_xxx.mp4 --platform instagram
    python3 publish.py --video output/journal_xxx.mp4 --platform all

Variables d'environnement requises :
    YouTube   : YOUTUBE_TOKEN_JSON   (contenu du token.json OAuth2, en base64)
                YOUTUBE_CLIENT_JSON  (contenu du client_secrets.json, en base64)
    Instagram : INSTAGRAM_USER_ID    (ID numérique du compte)
                INSTAGRAM_TOKEN      (token longue durée 60j)
                VIDEO_PUBLIC_URL     (URL publique du MP4 — requis par Meta)
"""

import os, sys, json, time, argparse, base64, tempfile, subprocess
from pathlib import Path
from datetime import datetime


# ═══════════════════════════════════════════════════════════════
#  UTILS
# ═══════════════════════════════════════════════════════════════

def log(msg: str, icon: str = "▶"):
    print(f"  {icon}  {msg}", flush=True)

def env_required(key: str) -> str:
    val = os.getenv(key, "").strip()
    if not val:
        raise EnvironmentError(
            f"Variable d'environnement manquante : {key}\n"
            f"Ajoute-la dans GitHub → Settings → Secrets → Actions"
        )
    return val

def decode_b64_env(key: str) -> dict:
    """Décode une variable d'env base64 → dict JSON."""
    raw = env_required(key)
    try:
        return json.loads(base64.b64decode(raw).decode())
    except Exception:
        # Essayer directement comme JSON
        try:
            return json.loads(raw)
        except Exception as e:
            raise ValueError(f"Impossible de décoder {key} : {e}")


def load_metadata(video_path: str) -> dict:
    """
    Cherche le metadata.json généré par le pipeline (titre YouTube,
    description avec sommaire du jour, caption Instagram, hashtags) :
    1. à côté du MP4
    2. dans ses dossiers parents (cas de l'artifact téléchargé par publish.yml)
    3. dans ./output/
    Retourne {} si introuvable — les valeurs par défaut génériques
    prendront le relais.
    """
    vp = Path(video_path).resolve()
    candidates = [
        vp.parent / "metadata.json",
        vp.parent.parent / "metadata.json",
        Path("output") / "metadata.json",
        Path("downloaded") / "metadata.json",
    ]
    for c in candidates:
        try:
            if c.exists():
                with open(c, encoding="utf-8") as f:
                    meta = json.load(f)
                log(f"Métadonnées chargées : {c}", "📝")
                return meta
        except Exception as e:
            log(f"metadata.json illisible ({c}) : {e}", "⚠️")
    log("Pas de metadata.json — titres/descriptions génériques utilisés", "ℹ️")
    return {}


# ═══════════════════════════════════════════════════════════════
#  YOUTUBE
# ═══════════════════════════════════════════════════════════════

def upload_youtube(video_path: str, title: str, description: str) -> str | None:
    """
    Upload une vidéo sur YouTube via l'API Data v3.

    Prérequis :
    - YOUTUBE_CLIENT_JSON : client_secrets.json encodé en base64
    - YOUTUBE_TOKEN_JSON  : token.json OAuth2 encodé en base64
      (généré une fois en local avec generate_youtube_token.py)

    Retourne l'URL YouTube si succès, None sinon.
    """
    log("YouTube — initialisation...")

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        log("Packages manquants — pip install google-api-python-client google-auth", "❌")
        log("Ajoute ces packages dans requirements.txt", "💡")
        return None

    # ── Charger les credentials ──
    try:
        token_data  = decode_b64_env("YOUTUBE_TOKEN_JSON")
        client_data = decode_b64_env("YOUTUBE_CLIENT_JSON")
    except Exception as e:
        log(f"Erreur credentials : {e}", "❌")
        return None

    # Écrire les fichiers temporaires
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(token_data, f)
        token_path = f.name

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(client_data, f)
        client_path = f.name

    try:
        creds = Credentials.from_authorized_user_file(
            token_path,
            scopes=["https://www.googleapis.com/auth/youtube.upload"]
        )

        # Rafraîchir le token si expiré
        if creds.expired and creds.refresh_token:
            log("Rafraîchissement du token OAuth2...")
            creds.refresh(Request())
            # Sauvegarder le token rafraîchi
            with open(token_path, 'w') as f:
                f.write(creds.to_json())
            log("Token rafraîchi ✅")

        youtube = build("youtube", "v3", credentials=creds)

        # ── Métadonnées de la vidéo ──
        date_str = datetime.now().strftime("%d/%m/%Y")
        body = {
            "snippet": {
                "title":       title or f"Journal du Monde — {date_str}",
                "description": description or (
                    f"Journal d'actualités automatique du {date_str}\n\n"
                    "Généré automatiquement • Actualités mondiales • 5 infos essentielles\n\n"
                    "#actualités #journal #news #monde #information"
                ),
                "tags": ["actualités", "journal", "news", "monde", "information",
                         "france", "politique", "économie"],
                "categoryId": "25",   # 25 = News & Politics
                "defaultLanguage": "fr",
            },
            "status": {
                "privacyStatus":           "public",
                "selfDeclaredMadeForKids": False,
                "madeForKids":             False,
            }
        }

        # ── Upload ──
        log(f"Upload en cours : {Path(video_path).name} ({Path(video_path).stat().st_size / 1e6:.1f}MB)...")
        media = MediaFileUpload(
            video_path,
            mimetype="video/mp4",
            resumable=True,
            chunksize=5 * 1024 * 1024   # chunks de 5MB
        )

        request  = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                log(f"  Progression : {pct}%")

        video_id  = response["id"]
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        log(f"✅ Vidéo publiée : {video_url}", "🎬")
        return video_url

    except Exception as e:
        log(f"Erreur upload YouTube : {e}", "❌")
        return None
    finally:
        # Nettoyage fichiers temporaires
        for p in [token_path, client_path]:
            try:
                os.remove(p)
            except Exception:
                pass


# ═══════════════════════════════════════════════════════════════
#  INSTAGRAM
# ═══════════════════════════════════════════════════════════════

def upload_instagram(video_path: str, caption: str, public_url: str) -> str | None:
    """
    Publie un Reel sur Instagram via Meta Graph API.

    Prérequis :
    - INSTAGRAM_USER_ID  : ID numérique du compte (ex: "17841400000000000")
    - INSTAGRAM_TOKEN    : access token longue durée (60 jours)
    - VIDEO_PUBLIC_URL   : URL publique du MP4 (requis par Meta — héberger sur GitHub Release
                           ou un CDN public)

    Processus Meta (2 étapes obligatoires) :
    1. Créer un "media container" avec l'URL de la vidéo
    2. Attendre que Meta traite la vidéo (polling) puis publier

    Retourne l'ID du post si succès, None sinon.
    """
    import requests as req

    log("Instagram — initialisation...")

    try:
        user_id = env_required("INSTAGRAM_USER_ID")
        token   = env_required("INSTAGRAM_TOKEN")
        if not public_url:
            public_url = env_required("VIDEO_PUBLIC_URL")
    except EnvironmentError as e:
        log(str(e), "❌")
        return None

    date_str = datetime.now().strftime("%d/%m/%Y")
    if not caption:
        caption = (
            f"📰 Journal du Monde — {date_str}\n\n"
            "5 actualités essentielles en 3 minutes ⏱️\n\n"
            "#actualités #journal #news #monde #information #france"
        )

    base_url = f"https://graph.facebook.com/v19.0/{user_id}"

    # ── Étape 1 : Créer le container media ──
    log("Étape 1/2 — Création du container media...")
    r = req.post(f"{base_url}/media", data={
        "media_type":   "REELS",
        "video_url":    public_url,
        "caption":      caption,
        "share_to_feed": "true",
        "access_token": token,
    }, timeout=30)

    if r.status_code != 200:
        log(f"Erreur container : {r.status_code} — {r.text[:200]}", "❌")
        return None

    container_id = r.json().get("id")
    if not container_id:
        log(f"ID container absent : {r.json()}", "❌")
        return None

    log(f"Container créé : {container_id}")

    # ── Étape 2 : Attendre le traitement Meta (polling) ──
    log("Étape 2/2 — Attente traitement Meta (peut prendre 30-90s)...")
    max_wait  = 120   # secondes max
    interval  = 10
    elapsed   = 0
    status    = ""

    while elapsed < max_wait:
        time.sleep(interval)
        elapsed += interval

        r = req.get(f"https://graph.facebook.com/v19.0/{container_id}", params={
            "fields":       "status_code,status",
            "access_token": token,
        }, timeout=15)

        if r.status_code != 200:
            log(f"Polling erreur : {r.status_code}", "⚠️")
            continue

        data   = r.json()
        status = data.get("status_code", "")
        log(f"  Status : {status} ({elapsed}s écoulées)")

        if status == "FINISHED":
            break
        elif status in ("ERROR", "EXPIRED"):
            log(f"Traitement Meta échoué : {data.get('status', status)}", "❌")
            return None

    if status != "FINISHED":
        log(f"Timeout — Meta n'a pas fini le traitement en {max_wait}s", "❌")
        return None

    # ── Étape 3 : Publier ──
    r = req.post(f"{base_url}/media_publish", data={
        "creation_id":  container_id,
        "access_token": token,
    }, timeout=30)

    if r.status_code != 200:
        log(f"Erreur publication : {r.status_code} — {r.text[:200]}", "❌")
        return None

    post_id = r.json().get("id")
    log(f"✅ Reel publié — ID : {post_id}", "🎬")
    log(f"   Visible sur : https://www.instagram.com/reels/")
    return post_id


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Publication automatique journal vidéo")
    parser.add_argument("--video",      required=True,  help="Chemin vers le MP4")
    parser.add_argument("--platform",   default="all",  help="youtube | instagram | all")
    parser.add_argument("--title",      default="",     help="Titre YouTube")
    parser.add_argument("--caption",    default="",     help="Caption Instagram")
    parser.add_argument("--public-url", default="",     help="URL publique du MP4 (Instagram)")
    args = parser.parse_args()

    video_path = args.video
    if not Path(video_path).exists():
        print(f"❌ Vidéo introuvable : {video_path}")
        sys.exit(1)

    size_mb = Path(video_path).stat().st_size / 1e6
    print(f"""
╔══════════════════════════════════════════════════════════════════════╗
║        📤 PUBLICATION AUTOMATIQUE — Journal Vidéo                   ║
╚══════════════════════════════════════════════════════════════════════╝
  Vidéo    : {video_path} ({size_mb:.1f} MB)
  Platform : {args.platform}
  Date     : {datetime.now().strftime('%d/%m/%Y %H:%M')}
""")

    # ── Métadonnées générées par le pipeline (titre du jour, sommaire...) ──
    meta        = load_metadata(video_path)
    title       = args.title   or meta.get("titre_video", "")
    description = meta.get("description", "")
    caption     = args.caption or meta.get("caption", "")

    results = {}
    platform = args.platform.lower()

    # ── YouTube ──
    if platform in ("youtube", "all"):
        print("📺 YOUTUBE")
        print("─" * 60)
        url = upload_youtube(video_path, title, description)
        results["youtube"] = url
        print()

    # ── Instagram ──
    if platform in ("instagram", "all"):
        print("📸 INSTAGRAM REELS")
        print("─" * 60)
        post_id = upload_instagram(video_path, caption, args.public_url)
        results["instagram"] = post_id
        print()

    # ── Résumé ──
    print("╔══════════════════════════════════════════════════════════════════════╗")
    print("║  📊 RÉSUMÉ PUBLICATION")
    print("╠══════════════════════════════════════════════════════════════════════╣")
    for platform, result in results.items():
        status = f"✅ {result}" if result else "❌ Échec"
        print(f"║  {platform.upper():<12} : {status}")
    print("╚══════════════════════════════════════════════════════════════════════╝")

    # Exit code non-zero si toutes les publications ont échoué
    if all(v is None for v in results.values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
