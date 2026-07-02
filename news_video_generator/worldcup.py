"""
worldcup.py — Édition spéciale COUPE DU MONDE 2026.

Même pipeline que le journal quotidien (photos → voix → vidéo), mais avec :
- des feeds RSS 100% football/sport
- un prompt Groq spécialisé qui structure la vidéo en 3 blocs :
    1-2 segments "RÉSULTATS"   → matchs joués (avec les scores)
    1-2 segments "AUJOURD'HUI" → affiches du jour (équipes, enjeu, horaire)
    1   segment  "STAT/JOUEUR" → statistique marquante ou joueur en vue
- des mots-clés photo TRÈS visuels orientés football (stade, supporters,
  célébration, trophée) pour des images qui parlent immédiatement

Le JSON produit garde exactement le même schéma que news.py → toutes les
étapes suivantes (photos, audio, rendu, métadonnées) sont réutilisées
telles quelles.
"""
import re
import json
from datetime import datetime

import requests

from .config import date_fr
from .news import _fetch_one_feed, GROQ_MODELS

# Feeds sport/football uniquement. La collecte parallèle de news.py
# tolère les feeds morts — on en met large.
WC_RSS_FEEDS = [
    ("L'Équipe",   "https://www.lequipe.fr/rss/actu_rss_Football.xml"),
    ("RMC Sport",  "https://rmcsport.bfmtv.com/rss/football/"),
    ("BBC Sport",  "https://feeds.bbci.co.uk/sport/football/rss.xml"),
    ("Le Monde",   "https://www.lemonde.fr/football/rss_full.xml"),
    ("France24",   "https://www.france24.com/fr/sports/rss"),
    ("Eurosport",  "https://www.eurosport.fr/football/rss.xml"),
    ("Foot365",    "https://www.football365.fr/feed"),
    ("So Foot",    "https://www.sofoot.com/rss.xml"),
]


def fetch_worldcup_rss(n: int = 30) -> list[dict]:
    """Scrape les feeds football en parallèle (5 articles par feed :
    les résultats et les avant-matchs sont souvent des articles distincts)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    print("  ⚽ Scraping RSS football (parallèle)...")
    per_source: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=len(WC_RSS_FEEDS)) as ex:
        futures = {ex.submit(_fetch_one_feed, s, u, 5): s for s, u in WC_RSS_FEEDS}
        for fut in as_completed(futures):
            per_source[futures[fut]] = fut.result()

    results, seen = [], set()
    for source, _ in WC_RSS_FEEDS:
        for art in per_source.get(source, []):
            if art["titre_brut"] in seen:
                continue
            seen.add(art["titre_brut"])
            results.append(art)

    ok = sum(1 for v in per_source.values() if v)
    print(f"  ✅ {len(results)} articles football collectés ({ok}/{len(WC_RSS_FEEDS)} sources OK)")
    return results[:n]


def structure_worldcup_with_groq(articles: list[dict], api_key: str) -> dict | None:
    """Structure les articles football en émission Spécial Coupe du Monde."""
    if not api_key:
        return None

    today = date_fr(datetime.now())
    articles_txt = "\n".join(
        f"{i+1}. [{a['source']}] {a['titre_brut']} — {a['desc_brute'][:150]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Tu es un journaliste sportif TV spécialiste du football. Nous sommes le {today}, en pleine COUPE DU MONDE 2026 (États-Unis / Mexique / Canada).

Voici des articles RSS football récents :
{articles_txt}

Construis une émission "Spécial Coupe du Monde" de 5 segments, EN PRIORISANT les infos liées à la Coupe du Monde 2026 :
- Segments 1-2 : RÉSULTATS — matchs de la Coupe du Monde déjà joués (donne les SCORES EXACTS s'ils apparaissent dans les articles, les buteurs si mentionnés). Ne JAMAIS inventer un score absent des articles.
- Segments 3-4 : AUJOURD'HUI — les affiches du jour ou à venir (équipes, enjeu, phase de la compétition, horaire si mentionné).
- Segment 5 : LA STAT — une statistique marquante, un record ou un joueur en vue du tournoi (uniquement si présent dans les articles).
Si les articles ne couvrent pas assez la Coupe du Monde, complète avec les actualités football les plus importantes en le disant clairement.

Style : journaliste sportif TV, dynamique, précis. IMPORTANT : le résumé sera lu par une voix off SANS le titre (le titre n'apparaît qu'à l'écran) — il doit donc être 100% autonome à l'oral :
- La PREMIÈRE phrase nomme les équipes/le joueur et donne le fait principal (ex: "La France a renversé le Brésil deux buts à un en quart de finale.").
- 2-3 phrases courtes sujet-verbe-complément, 45-60 mots, écris les scores en toutes lettres dans le résumé ("deux buts à un").
- Interdits : style télégraphique, phrases nominales, débuter par un pronom ou une référence vague.
Titres courts et percutants pour l'écran (max 8 mots, ex: "France 2 à 1 Brésil : qualification arrachée").

RÈGLES D'ÉCRITURE ORALE (le texte sera LU À VOIX HAUTE par une synthèse vocale) :
- Scores TOUJOURS avec "à" : "2 à 1", "3 à 0" — JAMAIS "2-1" ni "2:1"
- Séances de tirs au but : "4 à 2 aux tirs au but" — jamais "t.a.b."
- Noms de pays en toutes lettres : "République démocratique du Congo" (jamais "RD Congo"), "États-Unis" (jamais "USA")
- Aucun sigle ni abréviation non lexicalisé, "contre" au lieu de "vs"

Pour keywords_photo : mots-clés anglais TRÈS VISUELS de football, dans cet esprit :
"soccer stadium floodlights", "football fans celebrating flags", "soccer player celebration",
"goalkeeper diving save", "soccer ball goal net", "world cup trophy gold", "penalty kick".
Le premier mot-clé doit capturer l'AMBIANCE du segment (victoire → célébration, affiche → stade plein, stat → action de jeu). Jamais de noms de joueurs ou de pays dans les keywords.

Réponds UNIQUEMENT avec ce JSON :
{{
  "news": [
    {{
      "titre": "Titre court percutant (max 8 mots)",
      "resume": "Résumé oral autonome 45-60 mots (première phrase = équipes + fait principal)",
      "source": "Nom du média",
      "categorie": "sport",
      "keywords_photo": ["keyword1", "keyword2", "keyword3"]
    }}
  ],
  "intro": "Accroche d'ouverture Coupe du Monde dynamique (15 mots max)",
  "outro": "Phrase de clôture donnant rendez-vous demain (10 mots max)",
  "titre_video": "Titre YouTube accrocheur Coupe du Monde (max 90 caractères, avec la date)",
  "hashtags": ["coupedumonde2026", "5 à 8 hashtags football français SANS le symbole #"]
}}"""

    headers = {"Authorization": f"Bearer {api_key}",
               "Content-Type": "application/json"}

    for model in GROQ_MODELS:
        for attempt in (1, 2):
            body = {
                "model": model,
                "max_tokens": 2500,
                "temperature": 0.4,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            }
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers, json=body, timeout=30
                )
                if r.status_code == 429:
                    import time as _t; _t.sleep(3 * attempt)
                    continue
                if r.status_code != 200:
                    print(f"  ⚠️  Groq HTTP {r.status_code} ({model}) : {r.text[:150]}")
                    break
                raw = r.json()["choices"][0]["message"]["content"].strip()
                raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                    if result.get("news"):
                        print(f"  ✅ {len(result['news'])} segments Mondial via Groq ({model})")
                        return result
            except Exception as e:
                print(f"  ⚠️  Groq erreur ({model}, essai {attempt}) : {e}")
    return None


def get_worldcup_news(config: dict) -> dict:
    """Pipeline de collecte de l'édition Spécial Coupe du Monde."""
    print("\n⚽ ÉTAPE 1 — Collecte Spécial Coupe du Monde 2026...")

    raw = fetch_worldcup_rss(30)

    if config["GROQ_API_KEY"]:
        print("  🤖 Structuration Mondial via Groq...")
        result = structure_worldcup_with_groq(raw, config["GROQ_API_KEY"])
        if result and len(result.get("news", [])) >= 3:
            news = result["news"][:config["TOP_N"]]
            result["news"] = news
            print(f"\n📋 Émission du jour ({len(news)} segments) :")
            for i, item in enumerate(news, 1):
                print(f"  {i:2}. [{item.get('source','?')}] {item['titre'][:65]}")
            return result

    # Fallback : RSS brut football sans IA
    print("  ⚠️  Groq non disponible → RSS football brut (qualité réduite)")
    if raw:
        n = config["TOP_N"]
        news = []
        for a in raw[:n]:
            news.append({
                "titre":          a["titre_brut"][:80],
                "resume":         a["desc_brute"][:200],
                "source":         a["source"],
                "categorie":      "sport",
                "keywords_photo": ["soccer stadium floodlights", "football fans", "soccer"],
            })
        return {
            "news":  news,
            "intro": f"Spécial Coupe du Monde, voici l'actualité football du {date_fr(datetime.now())}.",
            "outro": "Rendez-vous demain pour la suite du Mondial.",
            "titre_video": f"⚽ Coupe du Monde 2026 — {date_fr(datetime.now(), with_weekday=False)}",
            "hashtags": ["coupedumonde2026", "football", "mondial2026", "worldcup", "sport"],
        }

    # Démo statique (aucune source disponible)
    print("  ⚠️  Aucune source disponible → segments de démo")
    return _demo_worldcup(config["TOP_N"])


def _demo_worldcup(n: int) -> dict:
    topics = [
        ("France 2 à 1 Brésil : qualification arrachée",
         "Les Bleus renversent le Brésil en quart de finale grâce à un doublé dans les vingt dernières minutes. Un match d'une intensité rare, conclu dans une ambiance électrique au MetLife Stadium.",
         "L'Équipe", ["football fans celebrating flags", "soccer stadium floodlights", "celebration"]),
        ("Espagne-Argentine, choc des demi-finales",
         "L'affiche du jour oppose deux géants du football mondial. L'Espagne, invaincue depuis quatorze matchs, défie l'Argentine tenante du titre. Coup d'envoi ce soir dans un stade à guichets fermés.",
         "RMC Sport", ["soccer stadium full crowd", "football pitch night", "stadium"]),
        ("Le Maroc continue de surprendre",
         "Nouvelle sensation du tournoi, le Maroc s'est qualifié pour le dernier carré après une séance de tirs au but héroïque. Son gardien, auteur de trois arrêts, devient l'homme du Mondial.",
         "France24", ["goalkeeper diving save", "soccer goal net", "football"]),
        ("Dix buts : record en vue",
         "Avec dix réalisations depuis le début de la compétition, l'attaquant vedette n'est plus qu'à trois longueurs du record historique de Just Fontaine, établi en 1958. Une performance exceptionnelle.",
         "BBC Sport", ["soccer player celebration", "soccer ball goal", "football action"]),
        ("La finale se jouera à New York",
         "Le MetLife Stadium accueillera la finale dimanche devant 82 000 spectateurs. Les organisateurs annoncent un dispositif exceptionnel et une cérémonie de clôture inédite pour ce Mondial nord-américain.",
         "FIFA", ["world cup trophy gold", "stadium aerial view", "soccer"]),
    ]
    news = [{"titre": t[0], "resume": t[1], "source": t[2],
             "categorie": "sport", "keywords_photo": t[3]} for t in topics[:n]]
    return {
        "news":  news,
        "intro": "Bienvenue dans votre Spécial Coupe du Monde, résultats, affiches et stats du jour.",
        "outro": "Rendez-vous demain pour la suite du Mondial.",
        "titre_video": f"⚽ Coupe du Monde 2026 — {date_fr(datetime.now(), with_weekday=False)}",
        "hashtags": ["coupedumonde2026", "football", "mondial2026", "worldcup", "sport"],
    }
