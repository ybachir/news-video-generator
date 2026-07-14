"""
news.py — ÉTAPE 1 : Collecte & structuration des actualités.

RSS feeds  →  Groq (Llama 3.3, gratuit)  →  JSON propre, avec fallback
RSS brut puis démo statique si aucune source n'est disponible.
"""
import re
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import feedparser

from .config import date_fr

RSS_FEEDS = [
    ("Le Monde",     "https://www.lemonde.fr/rss/une.xml"),
    ("France24",     "https://www.france24.com/fr/rss"),
    ("BBC Monde",    "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("France Info",  "https://www.francetvinfo.fr/titres.rss"),
    ("Al Jazeera",   "https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Guardian", "https://www.theguardian.com/world/rss"),
    ("RFI",          "https://www.rfi.fr/fr/rss-podcasts/rfi-monde"),
    ("DW",           "https://rss.dw.com/rdf/rss-en-all"),
    ("Euronews",     "https://feeds.feedburner.com/euronews/fr/home/"),
    ("Le Figaro",    "https://www.lefigaro.fr/rss/figaro_actualites.xml"),
]

# feedparser.parse(url) n'a AUCUN timeout : un seul feed lent peut bloquer
# le pipeline plusieurs minutes sur le runner CI. On télécharge donc
# nous-mêmes avec requests (timeout strict) puis on parse les bytes.
RSS_TIMEOUT = 10
RSS_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NewsVideoBot/1.0)"}


def _fetch_one_feed(source: str, url: str, per_feed: int = 3) -> list[dict]:
    """Télécharge et parse UN feed RSS avec timeout strict."""
    out = []
    try:
        r = requests.get(url, timeout=RSS_TIMEOUT, headers=RSS_HEADERS)
        if r.status_code != 200:
            return out
        feed = feedparser.parse(r.content)
        for entry in feed.entries[:per_feed]:
            title = entry.get("title", "").strip()
            if not title:
                continue
            desc = re.sub(r"<[^>]+>", "",
                          entry.get("summary", "") or
                          entry.get("description", "")).strip()
            out.append({
                "titre_brut": title[:200],
                "desc_brute": desc[:400] if desc else title,
                "source": source,
            })
    except Exception:
        pass
    return out


def fetch_rss_raw(n: int = 20) -> list[dict]:
    """Scrape les RSS feeds EN PARALLÈLE et retourne les articles bruts.

    Parallélisation (10 feeds simultanés) : la collecte passe de ~30-60s
    séquentiels à ~5-10s, et un feed mort/lent ne bloque plus les autres.
    L'ordre des sources RSS_FEEDS est préservé dans le résultat (priorité
    aux sources en tête de liste)."""
    print("  📡 Scraping RSS feeds (parallèle)...")
    per_source: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=len(RSS_FEEDS)) as ex:
        futures = {ex.submit(_fetch_one_feed, s, u): s for s, u in RSS_FEEDS}
        for fut in as_completed(futures):
            per_source[futures[fut]] = fut.result()

    results, seen = [], set()
    for source, _ in RSS_FEEDS:           # ré-ordonner selon la priorité des sources
        for art in per_source.get(source, []):
            if art["titre_brut"] in seen:
                continue
            seen.add(art["titre_brut"])
            results.append(art)

    ok_feeds = sum(1 for v in per_source.values() if v)
    print(f"  ✅ {len(results)} articles RSS collectés ({ok_feeds}/{len(RSS_FEEDS)} sources OK)")
    return results[:n]


# Modèles Groq essayés dans l'ordre : si le 70B est décommissionné ou
# rate-limité, on retombe sur le 8B instant (qualité moindre mais toujours
# très correcte pour de la structuration JSON).
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]


def structure_with_groq(articles: list[dict], api_key: str, n: int) -> dict | None:
    """
    Envoie les articles bruts à Groq (gratuit) pour :
    - sélectionner les n plus importants
    - réécrire en style journaliste TV
    - classer par catégorie
    - extraire les keywords photo
    - générer les métadonnées de publication (titre YouTube, hashtags)
    """
    if not api_key:
        return None

    today = date_fr(datetime.now(), with_weekday=False)
    articles_txt = "\n".join(
        f"{i+1}. [{a['source']}] {a['titre_brut']} — {a['desc_brute'][:150]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Tu es le rédacteur en chef d'un média d'actualité nouvelle génération sur YouTube et TikTok, dans l'esprit des chaînes d'info les plus vues de France : RAPIDE, FACILE, ACCESSIBLE. Ton public a 15-35 ans. Nous sommes le {today}.

Voici {len(articles)} articles RSS bruts :
{articles_txt}

Sélectionne les {n} actualités les plus importantes et variées, et ORDONNE-LES comme les grandes chaînes d'actu YouTube :
- L'actu la PLUS importante du jour en premier (c'est l'accroche qui retient le spectateur).
- Si possible, termine par une note plus légère ou positive (culture, science, sport, bonne nouvelle).
Réécris chaque résumé POUR L'OREILLE : il sera lu par une voix off SANS le titre (le titre n'apparaît qu'à l'écran). Règles impératives :
- Le résumé doit être 100% autonome à l'oral : la PREMIÈRE phrase nomme clairement le sujet (pays, personne, institution).
- 2-3 phrases courtes sujet-verbe-complément, 45-60 mots, factuel, rythme de présentateur.
- TON "rapide, facile, accessible" : vocabulaire courant, zéro jargon. Si un terme technique est indispensable, explique-le en quelques mots dans la foulée ("l'euro numérique, c'est-à-dire une version électronique de la monnaie...").
- Donne le contexte essentiel en une demi-phrase quand il le faut ("pour rappel, ...").
- Neutre et factuel, aucune opinion.
- Interdits : style télégraphique, phrases nominales, débuter par un pronom ("Il", "Elle", "Ils") ou une référence vague ("Cette décision...").

Pour transition : écris la phrase d'ACCROCHE ORALE que le présentateur dit juste AVANT le résumé de ce sujet (2-6 mots + virgule finale).

RÈGLE DE COHÉRENCE (la plus importante — vérifie-la sujet par sujet) : compare CE sujet au sujet qui le précède immédiatement dans ta liste (utilise le champ "pays" que tu vas toi-même renseigner pour chaque sujet).
- N'utilise un mot qui annonce un CHANGEMENT ("cette fois", "maintenant", "Direction...", "Changement de registre") QUE si le pays, le lieu ou le thème a VRAIMENT changé par rapport au sujet précédent.
- Erreur à ne jamais commettre : si le sujet précédent parlait déjà de la France, n'écris pas "En France cette fois," pour le sujet suivant — "cette fois" implique à tort qu'on vient de quitter un autre endroit. Écris plutôt un connecteur additif : "Toujours en France,", "Autre actualité française,", "Également dans le pays,".
- Si le sujet précédent parlait d'un autre pays/thème et que celui-ci change vraiment de sujet, LÀ le pivot géographique/thématique est justifié ("Direction le Brésil,", "Changement de registre,").
- En cas de doute, préfère un connecteur neutre qui ne prétend rien sur la continuité ("Autre actualité qui a marqué la journée,", "On note aussi,") plutôt qu'un faux pivot.

Autres règles :
- Jamais une formule mécanique répétée à l'identique ("On commence"/"On continue" à chaque sujet = interdit).
- Le tout premier sujet peut être une accroche d'ouverture directe ("Premier sujet ce {today},", "On démarre avec une actualité majeure,") — jamais littéralement "On commence,".
- Le dernier sujet peut signaler la fin ("Et pour terminer,", "On finit sur une note plus légère,") SANS que ce soit obligatoire ni identique d'une vidéo à l'autre.

RÈGLES D'ÉCRITURE ORALE (le texte sera LU À VOIX HAUTE par une synthèse vocale) :
- Jamais de plages ou scores avec tiret : écris "2 à 1", "de 10 à 15" — jamais "2-1" ni "10-15"
- Noms de pays et d'institutions en toutes lettres : "République démocratique du Congo" (jamais "RD Congo"), "États-Unis" (jamais "USA")
- Aucun sigle ni abréviation non lexicalisé, "contre" au lieu de "vs"

Pour photo_query : décris en anglais LA SCÈNE PRÉCISE qu'on devrait voir à l'écran
pour ce sujet (3-6 mots, lieu/objet/action CONCRETS et photographiables) :
- ✅ "european parliament chamber interior", "container ship port cranes",
  "wildfire smoke forest aerial", "stock exchange trading screens"
- ❌ concepts abstraits ("economy", "tension"), noms de personnes, mots génériques ("news")
Pour keywords_photo : 3 mots-clés anglais de repli, du plus spécifique au plus général.

Réponds UNIQUEMENT avec ce JSON (sans markdown, sans backticks) :
{{
  "news": [
    {{
      "titre": "Titre court percutant (max 8 mots)",
      "pays": "Pays principal concerné par ce sujet (ex: \"France\", \"États-Unis\") ou \"International\" si aucun pays unique ne domine",
      "transition": "Accroche orale contextuelle avant ce sujet (2-6 mots + virgule)",
      "resume": "Résumé oral autonome 45-60 mots (première phrase = le sujet nommé)",
      "source": "Nom du média",
      "categorie": "politique|economie|science|technologie|sport|culture|environnement|societe|monde",
      "photo_query": "scène précise en anglais 3-6 mots",
      "keywords_photo": ["mot_anglais1", "mot_anglais2", "mot_anglais3"]
    }}
  ],
  "intro": "Accroche directe SANS cérémonie, 10-14 mots, qui annonce qu'on fait le tour de l'essentiel du jour (ex: 'Voici l'essentiel de l'actu de ce {today}, en trois minutes.')",
  "outro": "Clôture avec rendez-vous quotidien, 8-12 mots (ex: 'C'était l'essentiel du jour. On se retrouve demain.')",
  "titre_video": "Titre YouTube au format des chaînes d'actu : 'Sujet 1, sujet 2, sujet 3… Les {n} actus du jour ({today})' — max 95 caractères, sujets en 1-3 mots chacun",
  "hashtags": ["actualités", "5 à 8 hashtags français SANS le symbole #"]
}}"""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    for model in GROQ_MODELS:
        for attempt in (1, 2):
            body = {
                "model": model,
                "max_tokens": 2500,
                "temperature": 0.4,
                # Force le modèle à renvoyer du JSON valide (supporté par Groq)
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            }
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers, json=body, timeout=30
                )
                if r.status_code == 429:
                    print(f"  ⚠️  Groq rate-limit ({model}) — nouvel essai...")
                    import time as _t; _t.sleep(3 * attempt)
                    continue
                if r.status_code != 200:
                    print(f"  ⚠️  Groq HTTP {r.status_code} ({model}) : {r.text[:150]}")
                    break   # essayer le modèle suivant
                raw = r.json()["choices"][0]["message"]["content"].strip()
                raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                    if result.get("news"):
                        print(f"  ✅ {len(result['news'])} news structurées via Groq ({model})")
                        return result
            except Exception as e:
                print(f"  ⚠️  Groq erreur ({model}, essai {attempt}) : {e}")
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
                "pays":           "International",
                "resume":         a["desc_brute"][:200],
                "source":         a["source"],
                "categorie":      "monde",
                "keywords_photo": words or ["world", "news"],
            })
        date_str = date_fr(datetime.now())
        return {
            "news":  news,
            "intro": f"Voici l'essentiel de l'actu du {date_str}, en trois minutes.",
            "outro": "C'était l'essentiel du jour. On se retrouve demain.",
            "titre_video": f"Les {len(news)} actus du jour ({date_fr(datetime.now(), with_weekday=False)})",
            "hashtags": ["actualités", "journal", "news", "monde", "information"],
        }

    # 4. Démo statique
    print("  ⚠️  Aucune source disponible → news de démo")
    return _demo_news(n)


def _demo_news(n: int) -> dict:
    topics = [
        ("Sommet climatique international", "International", "Premier sujet ce jour, un rendez-vous international majeur,",
         "Les dirigeants mondiaux se réunissent pour discuter de nouvelles mesures contre le changement climatique. Des engagements ambitieux sont attendus lors de cette session extraordinaire.", "ONU", "environnement", ["climate", "summit", "earth"]),
        ("Percée en intelligence artificielle", "International", "Du côté de la science maintenant,",
         "Des chercheurs annoncent une avancée majeure en IA générale. Cette technologie pourrait transformer la médecine, l'éducation et l'industrie dans les prochaines années.", "MIT Tech", "technologie", ["artificial", "intelligence", "robot"]),
        ("Tensions géopolitiques en Europe", "Europe", "En Europe maintenant,",
         "La diplomatie internationale s'intensifie face aux nouvelles tensions régionales. Des pourparlers d'urgence sont en cours entre les principales puissances.", "Reuters", "politique", ["diplomacy", "europe", "politics"]),
        ("Marchés financiers en turbulences", "International", "Du côté de l'économie,",
         "Les bourses mondiales enregistrent de fortes fluctuations suite aux annonces des banques centrales sur les taux d'intérêt.", "Bloomberg", "economie", ["stock", "market", "finance"]),
        ("Découverte scientifique sur Mars", "États-Unis", "Et pour terminer sur une note plus légère,",
         "La NASA confirme la présence de traces organiques sous la surface martienne, relançant le débat sur la vie extraterrestre.", "NASA", "science", ["mars", "space", "discovery"]),
    ]
    news = [{"titre": t[0], "pays": t[1], "transition": t[2], "resume": t[3], "source": t[4], "categorie": t[5], "keywords_photo": t[6]} for t in topics[:n]]
    return {
        "news":  news,
        "intro": f"Voici l'essentiel de l'actu du {date_fr(datetime.now(), with_weekday=False)}, en trois minutes.",
        "outro": "C'était l'essentiel du jour. On se retrouve demain.",
        "titre_video": f"Les {len(news)} actus du jour ({date_fr(datetime.now(), with_weekday=False)})",
        "hashtags": ["actualités", "journal", "news", "monde", "information"],
    }
