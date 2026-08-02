"""
topics.py — Édition "ZOOM SUR" : détection des sujets dominants du jour et
génération d'UNE vidéo approfondie ("deep dive") PAR sujet.

Contrairement au journal (5 actus survolées) ou aux éditions spéciales
worldcup/france (1 seule vidéo multi-sujets), ce module :

1. Scrape un pool RSS large (plus d'articles par source que le journal).
2. Demande à Groq de repérer entre 2 et 4 sujets qui reviennent chez
   PLUSIEURS sources différentes (signal de virité réel — pas un choix de
   thème fixe), et de regrouper les articles concernés par sujet.
3. Pour CHAQUE sujet retenu, envoie uniquement les articles qui lui sont
   liés (regroupés depuis plusieurs sources) à un second appel Groq qui
   construit un format "deep dive" de 2 à 4 segments — plus long et plus
   détaillé qu'un segment de journal classique — afin d'éviter le
   remplissage : on ne détaille QUE ce qui est effectivement corroboré
   par plusieurs articles.

Chaque sujet produit un script_data au même schéma que news.py → la suite
du pipeline (photos, audio, vidéo) est appelée une fois PAR sujet dans
__init__.py, sans aucune modification des autres modules.
"""
import re
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .config import date_fr
from .news import RSS_FEEDS, _fetch_one_feed, GROQ_MODELS

# Nombre de sujets à conserver : jamais moins de 2, jamais plus de 4 —
# ajusté selon ce que Groq trouve réellement corroboré par plusieurs
# sources ce jour-là (pas de nombre fixe imposé).
MIN_TOPICS = 2
MAX_TOPICS = 4
MIN_SOURCES_FOR_VIRAL = 2   # un sujet doit apparaître chez ≥2 sources distinctes


def fetch_topic_pool(per_feed: int = 6) -> list[dict]:
    """Scrape un pool RSS plus large que le journal (plus d'articles par
    source) pour avoir assez de matière à croiser entre sources."""
    print("  📡 Scraping RSS (pool élargi pour détection de sujets)...")
    per_source: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=len(RSS_FEEDS)) as ex:
        futures = {ex.submit(_fetch_one_feed, s, u, per_feed): s for s, u in RSS_FEEDS}
        for fut in as_completed(futures):
            per_source[futures[fut]] = fut.result()

    results, seen = [], set()
    for source, _ in RSS_FEEDS:
        for art in per_source.get(source, []):
            if art["titre_brut"] in seen:      # doublons exacts uniquement —
                continue                        # on GARDE les articles proches
            seen.add(art["titre_brut"])         # de sources différentes (c'est
            results.append(art)                 # le but du croisement)

    ok = sum(1 for v in per_source.values() if v)
    print(f"  ✅ {len(results)} articles collectés ({ok}/{len(RSS_FEEDS)} sources OK)")
    return results


def detect_daily_topics(articles: list[dict], api_key: str) -> list[dict] | None:
    """Demande à Groq de repérer les sujets corroborés par plusieurs
    sources. Retourne une liste de clusters {titre_sujet, indices,
    nb_sources}, triée par nb_sources décroissant (le plus recoupé =
    le plus viral en premier)."""
    if not api_key or not articles:
        return None

    numbered = "\n".join(
        f"{i+1}. [{a['source']}] {a['titre_brut']} — {a['desc_brute'][:120]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Tu es rédacteur en chef. Voici {len(articles)} articles RSS bruts collectés aujourd'hui, de sources différentes :
{numbered}

Identifie les sujets d'actualité qui reviennent chez PLUSIEURS sources DIFFÉRENTES (même événement traité sous des angles différents par au moins 2 médias distincts) — c'est le signal qu'un sujet domine réellement l'actualité du jour, quel que soit le thème (politique, catastrophe, sport, économie, buzz...).

Retourne entre 2 et 4 sujets maximum, ORDONNÉS du plus recoupé (le plus de sources différentes) au moins recoupé. N'invente aucun sujet arbitraire : base-toi uniquement sur les articles fournis. Si un sujet n'est mentionné que par une seule source, ne le retiens PAS (sauf si tu ne trouves vraiment aucun sujet avec ≥2 sources, auquel cas retourne les 2 sujets les plus solides que tu as, même mono-source, pour ne rien renvoyer de vide).

Pour chaque sujet, liste les NUMÉROS des articles ci-dessus qui s'y rapportent (un article ne doit appartenir qu'à un seul sujet).

Réponds UNIQUEMENT avec ce JSON :
{{
  "sujets": [
    {{
      "titre_sujet": "Description courte et neutre du sujet (5-10 mots)",
      "articles": [1, 4, 9]
    }}
  ]
}}"""

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for model in GROQ_MODELS:
        for attempt in (1, 2):
            body = {
                "model": model,
                "max_tokens": 1500,
                "temperature": 0.3,
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
                if not match:
                    continue
                result = json.loads(match.group(0))
                sujets = result.get("sujets", [])
                if not sujets:
                    continue

                # Revalidation côté Python : on ne fait PAS confiance
                # aveuglément au nombre de sources annoncé par le modèle,
                # on le recalcule depuis les indices d'articles réels.
                validated = []
                for s in sujets:
                    idxs = [i - 1 for i in s.get("articles", [])
                            if isinstance(i, int) and 1 <= i <= len(articles)]
                    if not idxs:
                        continue
                    sources = {articles[i]["source"] for i in idxs}
                    validated.append({
                        "titre_sujet": s.get("titre_sujet", "Sujet du jour")[:100],
                        "indices": idxs,
                        "nb_sources": len(sources),
                    })

                cross_sourced = [s for s in validated if s["nb_sources"] >= MIN_SOURCES_FOR_VIRAL]
                cross_sourced.sort(key=lambda s: s["nb_sources"], reverse=True)

                if len(cross_sourced) >= MIN_TOPICS:
                    print(f"  ✅ {len(cross_sourced)} sujet(s) multi-sources détecté(s) via Groq ({model})")
                    return cross_sourced[:MAX_TOPICS]

                # Repli : pas assez de sujets vraiment recoupés → on
                # complète avec les meilleurs trouvés (même mono-source)
                # pour toujours retourner au moins MIN_TOPICS sujets.
                validated.sort(key=lambda s: s["nb_sources"], reverse=True)
                if validated:
                    print(f"  ⚠️  Seulement {len(cross_sourced)} sujet(s) multi-sources — complété avec le reste")
                    return validated[:MAX_TOPICS]
            except Exception as e:
                print(f"  ⚠️  Groq erreur ({model}, essai {attempt}) : {e}")
    return None


def structure_topic_deepdive_with_groq(titre_sujet: str, articles: list[dict], api_key: str) -> dict | None:
    """Construit un script 'deep dive' (2 à 4 segments détaillés) pour UN
    seul sujet, à partir des articles de plusieurs sources qui le
    couvrent — permet d'aller dans le détail sans remplissage puisque
    chaque segment s'appuie sur du contenu réellement recoupé."""
    if not api_key:
        return None

    today = date_fr(datetime.now())
    articles_txt = "\n".join(
        f"{i+1}. [{a['source']}] {a['titre_brut']} — {a['desc_brute'][:300]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Tu es journaliste TV, spécialisé dans les formats "explainer" approfondis pour YouTube/TikTok (public 15-35 ans, ton RAPIDE, FACILE, ACCESSIBLE). Nous sommes le {today}.

Voici plusieurs articles de sources DIFFÉRENTES qui parlent tous du MÊME sujet : "{titre_sujet}"
{articles_txt}

Construis un format APPROFONDI ("deep dive") de 2 à 4 segments qui raconte CE sujet en détail — pas un survol de 15 secondes, un vrai éclairage complet :
- Premier segment (angle "contexte") : pose le sujet, ce qui s'est passé, qui est concerné.
- Segment(s) suivant(s) (angle "faits") : les faits précis, chiffres ou déclarations SI présents dans les articles. N'invente JAMAIS un chiffre, une citation ou un fait absent des articles fournis.
- Dernier segment (angle "enjeu" ou "suite") : pourquoi c'est important, ce qui pourrait se passer ensuite, la portée de l'événement.
Croise les informations des différentes sources pour enrichir chaque segment (angles complémentaires, contexte supplémentaire) — c'est tout l'intérêt d'avoir plusieurs articles sur un même sujet : ne te contente PAS de résumer un seul article isolé.

Résumés plus longs qu'un format classique : 60 à 90 mots par segment (au lieu de 45-60), mais toujours 100% autonomes à l'oral (lu par une voix off SANS le titre affiché à l'écran) :
- La PREMIÈRE phrase de chaque segment nomme clairement le sujet/lieu/personne concerné.
- Phrases courtes sujet-verbe-complément, factuel, rythme de présentateur.
- Neutre et factuel, aucune opinion.
- Interdits : style télégraphique, phrases nominales, débuter par un pronom vague ("Il", "Elle", "Cette décision...").

Pour transition : accroche orale (2-6 mots + virgule finale) cohérente avec la progression contexte → faits → enjeu. Jamais "On commence"/"On continue" répété mécaniquement. Le premier segment peut ouvrir directement sur le sujet.

RÈGLES D'ÉCRITURE ORALE (lu à voix haute par une synthèse vocale) :
- Scores/plages toujours avec "à" : "2 à 1", "de 10 à 15" — jamais de tiret
- Pays/institutions en toutes lettres, aucun sigle non lexicalisé, "contre" au lieu de "vs"

Pour photo_query : scène anglaise précise et photographiable (3-6 mots), liée SPÉCIFIQUEMENT à ce segment.
Pour keywords_photo : 3 mots-clés anglais de repli, du plus spécifique au plus général.

Réponds UNIQUEMENT avec ce JSON (sans markdown, sans backticks) :
{{
  "news": [
    {{
      "titre": "Titre court percutant (max 8 mots)",
      "angle": "contexte|faits|enjeu|suite",
      "transition": "Accroche orale (2-6 mots + virgule)",
      "resume": "Résumé oral autonome 60-90 mots",
      "source": "Nom du média principal (ou 'Sources multiples' si plusieurs à parts égales)",
      "categorie": "politique|economie|science|technologie|sport|culture|environnement|societe|monde",
      "photo_query": "scène précise en anglais 3-6 mots",
      "keywords_photo": ["mot_anglais1", "mot_anglais2", "mot_anglais3"]
    }}
  ],
  "intro": "Accroche d'ouverture 'Zoom sur' ce sujet, 10-14 mots (ex: 'Zoom sur {titre_sujet}, on vous explique tout.')",
  "outro": "Clôture courte, 8-12 mots (ex: 'Voilà pour ce zoom. On se retrouve bientôt.')",
  "titre_video": "Titre YouTube accrocheur centré UNIQUEMENT sur ce sujet (max 90 caractères, avec la date {today})",
  "bandeau": "Version courte du sujet en 2-4 mots MAJUSCULES pour l'écran (ex: 'ÉLECTIONS ANTICIPÉES')",
  "hashtags": ["5 à 8 hashtags français SANS le symbole # liés spécifiquement à ce sujet"]
}}"""

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

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
                    if result.get("news") and len(result["news"]) >= 2:
                        print(f"  ✅ Deep dive '{titre_sujet[:40]}' : {len(result['news'])} segments ({model})")
                        return result
            except Exception as e:
                print(f"  ⚠️  Groq erreur ({model}, essai {attempt}) : {e}")
    return None


def get_daily_deepdive_scripts(config: dict) -> list[dict]:
    """Pipeline complet : détecte les sujets dominants du jour puis
    construit un script 'deep dive' par sujet. Retourne une liste de
    {"script_data": ..., "slug": ...} — entre 2 et 4 éléments."""
    print("\n🔎 ÉTAPE 1 — Détection des sujets dominants du jour...")

    if not config["GROQ_API_KEY"]:
        print("  ⚠️  Pas de clé Groq → sujets de démo")
        return _demo_topics()

    pool = fetch_topic_pool()
    if not pool:
        print("  ⚠️  Aucun article RSS → sujets de démo")
        return _demo_topics()

    clusters = detect_daily_topics(pool, config["GROQ_API_KEY"])
    if not clusters:
        print("  ⚠️  Aucun sujet détecté → sujets de démo")
        return _demo_topics()

    print(f"  📋 {len(clusters)} sujet(s) retenu(s) :")
    for c in clusters:
        print(f"    • {c['titre_sujet']} ({c['nb_sources']} source(s))")

    results = []
    for i, c in enumerate(clusters, 1):
        articles = [pool[idx] for idx in c["indices"]]
        print(f"\n📝 SUJET {i}/{len(clusters)} — {c['titre_sujet']}")
        script_data = structure_topic_deepdive_with_groq(
            c["titre_sujet"], articles, config["GROQ_API_KEY"]
        )
        if script_data and len(script_data.get("news", [])) >= 2:
            results.append({"script_data": script_data, "slug": f"sujet{i}"})
        else:
            print(f"  ⚠️  Échec structuration — sujet ignoré")

    if len(results) < MIN_TOPICS:
        print(f"  ⚠️  Seulement {len(results)} sujet(s) structuré(s) avec succès → complément par démo")
        demo = _demo_topics()
        for d in demo:
            if len(results) >= MIN_TOPICS:
                break
            d["slug"] = f"sujet{len(results) + 1}"
            results.append(d)

    return results


def _demo_topics() -> list[dict]:
    """Deux sujets de démo statiques (aucune source disponible), au
    même schéma que la sortie réelle du pipeline."""
    today = date_fr(datetime.now())

    sujet1 = {
        "news": [
            {"titre": "Un accord international signé à Bruxelles", "angle": "contexte",
             "transition": "Premier zoom du jour,",
             "resume": "Plusieurs chefs d'État se sont retrouvés à Bruxelles pour signer un accord préparé depuis des mois. La cérémonie s'est tenue en fin de matinée devant la presse internationale, marquant l'aboutissement de longues négociations.",
             "source": "Sources multiples", "categorie": "politique",
             "keywords_photo": ["european union building brussels", "diplomats signing agreement", "politics"]},
            {"titre": "Ce que contient réellement le texte", "angle": "faits",
             "transition": "Dans le détail,",
             "resume": "Le texte prévoit un renforcement de la coopération économique entre les pays signataires, avec un calendrier de mise en œuvre échelonné sur trois ans. Plusieurs points restent encore soumis à ratification parlementaire dans certains pays.",
             "source": "Sources multiples", "categorie": "politique",
             "keywords_photo": ["document signing pen", "official agreement paper", "handshake"]},
            {"titre": "Les prochaines étapes attendues", "angle": "suite",
             "transition": "Et maintenant, quelle suite,",
             "resume": "Les parlements nationaux devront désormais approuver l'accord avant son entrée en vigueur définitive. Les observateurs s'attendent à des débats animés dans plusieurs pays, où l'opposition a déjà annoncé des réserves.",
             "source": "Sources multiples", "categorie": "politique",
             "keywords_photo": ["parliament chamber debate", "government building europe", "politics"]},
        ],
        "intro": "Zoom sur l'accord signé aujourd'hui à Bruxelles, on vous explique tout.",
        "outro": "Voilà pour ce zoom. On se retrouve bientôt pour un autre sujet.",
        "titre_video": f"🔎 Zoom sur l'accord de Bruxelles — {today}",
        "bandeau": "ACCORD BRUXELLES",
        "hashtags": ["zoomsur", "actualité", "europe", "politique", "international"],
    }

    sujet2 = {
        "news": [
            {"titre": "Une percée technologique confirmée", "angle": "contexte",
             "transition": "Deuxième zoom du jour,",
             "resume": "Une équipe de chercheurs annonce une avancée majeure dans un domaine suivi de près par plusieurs laboratoires concurrents. Plusieurs publications scientifiques indépendantes confirment ce jour la solidité des premiers résultats.",
             "source": "Sources multiples", "categorie": "technologie",
             "keywords_photo": ["research laboratory scientists", "technology innovation lab", "science"]},
            {"titre": "Pourquoi cette découverte change la donne", "angle": "faits",
             "transition": "Concrètement,",
             "resume": "Les premiers tests montrent des résultats nettement supérieurs aux méthodes existantes, avec un gain de performance mesuré par plusieurs équipes indépendantes. Les applications concrètes pourraient toucher plusieurs secteurs industriels dans les prochaines années.",
             "source": "Sources multiples", "categorie": "technologie",
             "keywords_photo": ["computer screen data analysis", "technology testing equipment", "innovation"]},
            {"titre": "Les prochaines étapes de recherche", "angle": "suite",
             "transition": "La suite maintenant,",
             "resume": "Les équipes annoncent une nouvelle phase de tests à plus grande échelle dans les prochains mois. Plusieurs partenaires industriels auraient déjà manifesté leur intérêt pour accompagner cette prochaine étape du projet.",
             "source": "Sources multiples", "categorie": "technologie",
             "keywords_photo": ["scientists team meeting", "future technology concept", "research"]},
        ],
        "intro": "Zoom sur cette avancée technologique qui fait parler, on vous explique tout.",
        "outro": "Voilà pour ce zoom. On se retrouve bientôt pour un autre sujet.",
        "titre_video": f"🔎 Zoom sur la percée technologique du jour — {today}",
        "bandeau": "PERCÉE TECH",
        "hashtags": ["zoomsur", "actualité", "technologie", "science", "innovation"],
    }

    return [
        {"script_data": sujet1, "slug": "sujet1"},
        {"script_data": sujet2, "slug": "sujet2"},
    ]
