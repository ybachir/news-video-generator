#!/usr/bin/env python3
"""
generate_youtube_token.py — Génère le token OAuth2 YouTube (à lancer UNE FOIS en local)

Usage :
    1. Télécharge client_secrets.json depuis Google Cloud Console
    2. Lance : python3 generate_youtube_token.py
    3. Autorise dans le navigateur
    4. Récupère youtube_token.json et client_secrets_b64.txt
    5. Ajoute dans GitHub Secrets :
         YOUTUBE_TOKEN_JSON  = contenu de youtube_token_b64.txt
         YOUTUBE_CLIENT_JSON = contenu de client_secrets_b64.txt

Prérequis :
    pip install google-api-python-client google-auth-oauthlib
"""

import os, sys, json, base64
from pathlib import Path


def main():
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError:
        print("❌ Package manquant :")
        print("   pip install google-api-python-client google-auth-oauthlib")
        sys.exit(1)

    client_file = "client_secrets.json"
    if not Path(client_file).exists():
        print(f"❌ Fichier introuvable : {client_file}")
        print()
        print("Pour l'obtenir :")
        print("  1. Va sur https://console.cloud.google.com")
        print("  2. Crée un projet (ou utilise un existant)")
        print("  3. Active 'YouTube Data API v3'")
        print("  4. Credentials → Create → OAuth 2.0 Client ID → Desktop App")
        print("  5. Télécharge le JSON et renomme-le client_secrets.json")
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

    print("🔐 Lancement du flow OAuth2 YouTube...")
    print("   Un navigateur va s'ouvrir pour autoriser l'accès.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(client_file, SCOPES)
    creds = flow.run_local_server(port=0)

    # Sauvegarder le token
    token_data = json.loads(creds.to_json())
    with open("youtube_token.json", "w") as f:
        json.dump(token_data, f, indent=2)

    # Encoder en base64 pour GitHub Secrets
    token_b64  = base64.b64encode(json.dumps(token_data).encode()).decode()
    client_b64 = base64.b64encode(Path(client_file).read_bytes()).decode()

    with open("youtube_token_b64.txt", "w") as f:
        f.write(token_b64)

    with open("client_secrets_b64.txt", "w") as f:
        f.write(client_b64)

    print("✅ Token généré avec succès !")
    print()
    print("Ajoute ces deux secrets dans GitHub :")
    print("  Settings → Secrets → Actions → New repository secret")
    print()
    print("  YOUTUBE_TOKEN_JSON  → contenu de youtube_token_b64.txt")
    print("  YOUTUBE_CLIENT_JSON → contenu de client_secrets_b64.txt")
    print()
    print("⚠️  Ne commite JAMAIS ces fichiers dans le repo !")
    print("   (ils sont déjà dans .gitignore)")


if __name__ == "__main__":
    main()
