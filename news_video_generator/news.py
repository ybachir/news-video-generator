"""
news.py — ÉTAPE 1 : Collecte & structuration des actualités.

RSS feeds  →  Groq (Llama 3.3, gratuit)  →  JSON propre, avec fallback
RSS brut puis démo statique si aucune source n'est disponible.
"""
import re
import json
from datetime import datetime

import requests
import feedparser

from .config import date_fr

RSS_FEEDS = [
    ("Le Monde",     "https://www.lemonde.fr/rss/une.xml"),
    ("France24",     "https://www.france24.com/fr/rss"),
    ("BBC Monde",    "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Reuters",      "https://feeds.reuters.com/reuters/topNews"),
    ("Al Jazeera",   "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("RFI",          "https://www.rfi.fr/fr/rss-podcasts/rfi-monde"),
    ("DW",           "https://rss.dw.com/rdf/rss-en-all"),
    ("Euronews",     "https://feeds.feedburner.com/euronews/fr/home/"),
    ("Le Figaro",    "https://www.lefigaro.fr/rss/figaro_actualites.xml"),
]


def fetch_rss_raw(n: int = 20) -> list[dict]:
    """Scrape les RSS feeds et retourne les articles bruts."""
    print("  📡 Scraping RSS feeds...")
    results, seen = [], set()
    for source, url in RSS_FEEDS:
        if len(results) >= n:
            break
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                title = entry.get("title", "").strip()
                if not title or title in seen:
                    continue
                seen.add(title)
                desc = re.sub(r"<[^>]+>", "",
                              entry.get("summary", "") or
                              entry.get("description", "")).strip()
                results.append({
                    "titre_brut": title[:200],
                    "desc_brute": desc[:400] if desc else title,
                    "source": source,
                })
        except Exception:
            continue
    print(f"  ✅ {len(results)} articles RSS collectés")
    return results[:n]


def structure_with_groq(articles: list[dict], api_key: str, n: int) -> dict | None:
    """
    Envoie les articles bruts à Groq (Llama 3.3, gratuit) pour :
    - sélectionner les n plus importants
    - réécrire en style journaliste TV
    - classer par catégorie
    - extraire les keywords photo
    """
    if not api_key:
        return None

    today = date_fr(datetime.now(), with_weekday=False)
    articles_txt = "\n".join(
        f"{i+1}. [{a['source']}] {a['titre_brut']} — {a['desc_brute'][:150]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Tu es un journaliste TV professionnel. Nous sommes le {today}.

Voici {len(articles)} articles RSS bruts :
{articles_txt}

Sélectionne les {n} actualités les plus importantes et variées.
Réécris chaque résumé en style journaliste TV (2-3 phrases, 40-55 mots, factuel, dynamique, concis).

Pour keywords_photo : choisis des mots-clés VISUELS et GÉNÉRIQUES adaptés à une
recherche sur banque d'images (ex: "stadium", "courtroom", "hospital", "protest",
"skyline", "factory", "soldiers") plutôt que des noms de pays ou de personnes précis,
qui renvoient souvent aucun résultat. Le premier mot-clé doit être le plus
représentatif visuellement du sujet.

Réponds UNIQUEMENT avec ce JSON (sans markdown, sans backticks) :
{{
  "news": [
    {{
      "titre": "Titre court percutant (max 8 mots)",
      "resume": "Résumé journaliste TV 40-55 mots",
      "source": "Nom du média",
      "categorie": "politique|economie|science|technologie|sport|culture|environnement|societe|monde",
      "keywords_photo": ["mot_anglais1", "mot_anglais2", "mot_anglais3"]
    }}
  ],
  "intro": "Accroche d'ouverture dynamique (15 mots max)",
  "outro": "Phrase de clôture (10 mots max)"
}}"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 2000,
        "temperature": 0.4,
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers=headers, json=body, timeout=30
        )
        data = r.json()
        raw = data["choices"][0]["message"]["content"].strip()
        # Nettoyer éventuels backticks
        raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
        # Extraire le JSON
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            print(f"  ✅ {len(result.get('news', []))} news structurées via Groq")
            return result
    except Exception as e:
        print(f"  ⚠️  Groq erreur : {e}")
    return None


def get_news(config: dict) -> dict:
    """Pipeline complet de collecte des news."""
    print("\n🔍 ÉTAPE 1 — Collecte & structuration des actualités...")
    n = config["TOP_N"]

    # 1. Scraper les RSS
    raw_articles = fetch_rss_raw(n * 3)

    # 2. Structurer avec Groq si clé disponible
    if config["GROQ_API_KEY"]:
        print("  🤖 Structuration via Groq (Llama 3.3)...")
        result = structure_with_groq(raw_articles, config["GROQ_API_KEY"], n)
        if result and len(result.get("news", [])) >= 3:
            news = result["news"][:n]
            print(f"\n📋 Top {len(news)} actualités :")
            for i, item in enumerate(news, 1):
                print(f"  {i:2}. [{item['source']}] {item['titre'][:65]}")
            return result

    # 3. Fallback : RSS brut sans IA
    print("  ⚠️  Groq non disponible → RSS brut (qualité réduite)")
    if raw_articles:
        news = []
        for a in raw_articles[:n]:
            words = [w for w in a["titre_brut"].split() if len(w) > 4][:3]
            news.append({
                "titre":          a["titre_brut"][:80],
                "resume":         a["desc_brute"][:200],
                "source":         a["source"],
                "categorie":      "monde",
                "keywords_photo": words or ["world", "news"],
            })
        date_str = date_fr(datetime.now())
        return {
            "news":  news,
            "intro": f"Bonjour, voici les {len(news)} actualités du {date_str}.",
            "outro": "Restez informés. À très bientôt.",
        }

    # 4. Démo statique
    print("  ⚠️  Aucune source disponible → news de démo")
    return _demo_news(n)


def _demo_news(n: int) -> dict:
    topics = [
        ("Sommet climatique international", "Les dirigeants mondiaux se réunissent pour discuter de nouvelles mesures contre le changement climatique. Des engagements ambitieux sont attendus lors de cette session extraordinaire.", "ONU", "environnement", ["climate", "summit", "earth"]),
        ("Percée en intelligence artificielle", "Des chercheurs annoncent une avancée majeure en IA générale. Cette technologie pourrait transformer la médecine, l'éducation et l'industrie dans les prochaines années.", "MIT Tech", "technologie", ["artificial", "intelligence", "robot"]),
        ("Tensions géopolitiques en Europe", "La diplomatie internationale s'intensifie face aux nouvelles tensions régionales. Des pourparlers d'urgence sont en cours entre les principales puissances.", "Reuters", "politique", ["diplomacy", "europe", "politics"]),
        ("Marchés financiers en turbulences", "Les bourses mondiales enregistrent de fortes fluctuations suite aux annonces des banques centrales sur les taux d'intérêt.", "Bloomberg", "economie", ["stock", "market", "finance"]),
        ("Découverte scientifique sur Mars", "La NASA confirme la présence de traces organiques sous la surface martienne, relançant le débat sur la vie extraterrestre.", "NASA", "science", ["mars", "space", "discovery"]),
    ]
    news = [{"titre": t[0], "resume": t[1], "source": t[2], "categorie": t[3], "keywords_photo": t[4]} for t in topics[:n]]
    return {
        "news":  news,
        "intro": f"Bienvenue dans votre journal du {date_fr(datetime.now(), with_weekday=False)}.",
        "outro": "Merci de votre fidélité. À demain.",
    }
