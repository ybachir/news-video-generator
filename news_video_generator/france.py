"""
france.py — Édition spéciale ACTUALITÉ FRANCE.

Même pipeline que le journal quotidien (photos → voix → vidéo), mais avec :
- des feeds RSS 100% France (politique nationale, société, économie
  française, régions) — aucune source internationale généraliste
- un prompt Groq spécialisé qui exclut l'actualité purement internationale
  (sauf si la France y est directement impliquée) et priorise le sujet
  le plus VIRAL du moment en France (recoupement multi-sources), exactement
  comme le journal principal — jamais un thème fixe imposé.

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

# Feeds France uniquement : politique nationale, société, régions,
# économie française. On évite volontairement les flux "monde" des
# mêmes médias (déjà couverts par le journal généraliste RSS_FEEDS).
FR_RSS_FEEDS = [
    ("Le Figaro France",   "https://www.lefigaro.fr/rss/figaro_flash-actu.xml"),
    ("France Info",        "https://www.francetvinfo.fr/france.rss"),
    ("Le Parisien",        "https://www.leparisien.fr/actus-en-direct.rss"),
    ("20 Minutes France",  "https://www.20minutes.fr/feeds/rss-france.xml"),
    ("BFMTV",              "https://www.bfmtv.com/rss/actualite/"),
    ("Ouest-France",       "https://www.ouest-france.fr/rss-en-continu.xml"),
    ("France Bleu",        "https://www.francebleu.fr/rss/a-la-une.xml"),
    ("Le Monde Politique", "https://www.lemonde.fr/politique/rss_full.xml"),
]


def fetch_france_rss(n: int = 30) -> list[dict]:
    """Scrape les feeds France en parallèle."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    print("  🇫🇷 Scraping RSS France (parallèle)...")
    per_source: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=len(FR_RSS_FEEDS)) as ex:
        futures = {ex.submit(_fetch_one_feed, s, u, 5): s for s, u in FR_RSS_FEEDS}
        for fut in as_completed(futures):
            per_source[futures[fut]] = fut.result()

    results, seen = [], set()
    for source, _ in FR_RSS_FEEDS:
        for art in per_source.get(source, []):
            if art["titre_brut"] in seen:
                continue
            seen.add(art["titre_brut"])
            results.append(art)

    ok = sum(1 for v in per_source.values() if v)
    print(f"  ✅ {len(results)} articles France collectés ({ok}/{len(FR_RSS_FEEDS)} sources OK)")
    return results[:n]


def structure_france_with_groq(articles: list[dict], api_key: str, n: int) -> dict | None:
    """Structure les articles France en émission Spécial France."""
    if not api_key:
        return None

    today = date_fr(datetime.now())
    articles_txt = "\n".join(
        f"{i+1}. [{a['source']}] {a['titre_brut']} — {a['desc_brute'][:150]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Tu es le rédacteur en chef d'un média d'actualité nouvelle génération sur YouTube et TikTok, spécialisé sur l'ACTUALITÉ FRANÇAISE exclusivement. Ton public a 15-35 ans, dans l'esprit des chaînes d'info les plus vues de France : RAPIDE, FACILE, ACCESSIBLE. Nous sommes le {today}.

Voici des articles RSS de médias français :
{articles_txt}

Sélectionne les {n} actualités FRANÇAISES les plus importantes et variées (politique nationale, société, économie française, régions, faits divers marquants, culture) :
- EXCLUS toute actualité purement internationale/étrangère qui ne concerne pas directement la France (sauf si un Français, une entreprise française ou une décision française y est impliquée).
- SUJET N°1 = l'actualité française la plus VIRALE du moment, c'est-à-dire celle qui revient le plus souvent, sous des angles différents, chez PLUSIEURS sources différentes dans la liste ci-dessus. N'aie AUCUN sujet de prédilection fixe : le sujet n°1 doit changer d'un jour à l'autre selon ce qui domine réellement les flux RSS de {today}, jamais un thème que tu choisirais par habitude.
- Si aucun sujet ne se détache clairement (pas de recoupement multi-sources), prends l'actu française la plus importante/récente en tête.
- Si possible, termine par une note plus légère (culture, société positive, sport français) — sauf si cette note légère est elle-même le sujet viral du jour.

Réécris chaque résumé POUR L'OREILLE : il sera lu par une voix off SANS le titre (le titre n'apparaît qu'à l'écran). Règles impératives :
- Le résumé doit être 100% autonome à l'oral : la PREMIÈRE phrase nomme clairement le sujet (ville, région, personne, institution française).
- 2-3 phrases courtes sujet-verbe-complément, 45-60 mots, factuel, rythme de présentateur.
- TON "rapide, facile, accessible" : vocabulaire courant, zéro jargon. Si un terme technique est indispensable, explique-le en quelques mots dans la foulée.
- Donne le contexte essentiel en une demi-phrase quand il le faut ("pour rappel, ...").
- Neutre et factuel, aucune opinion.
- Interdits : style télégraphique, phrases nominales, débuter par un pronom ("Il", "Elle", "Ils") ou une référence vague ("Cette décision...").

Pour transition : écris la phrase d'ACCROCHE ORALE que le présentateur dit juste AVANT le résumé de ce sujet (2-6 mots + virgule finale).

RÈGLE DE COHÉRENCE (vérifie-la sujet par sujet) : compare CE sujet au sujet qui le précède immédiatement dans ta liste (utilise le champ "region" que tu renseignes toi-même : ville, région, ou "National").
- N'utilise un mot qui annonce un CHANGEMENT ("cette fois", "maintenant", "Direction...", "Changement de registre") QUE si la région/ville ou le thème a VRAIMENT changé par rapport au sujet précédent.
- Si le sujet précédent parlait déjà de la même région/du national, n'écris pas un faux pivot géographique — utilise un connecteur additif ("Toujours en France,", "Autre actualité nationale,", "Également marquant aujourd'hui,").
- En cas de doute, préfère un connecteur neutre ("Autre actualité qui a marqué la journée,", "On note aussi,") plutôt qu'un faux pivot.

Autres règles :
- Jamais une formule mécanique répétée à l'identique ("On commence"/"On continue" à chaque sujet = interdit).
- Le tout premier sujet peut ouvrir directement ("Premier sujet ce {today},", "On démarre avec l'actualité qui fait parler en France,") — jamais littéralement "On commence,".
- Le dernier sujet peut signaler la fin ("Et pour terminer,", "On finit sur une note plus légère,") SANS que ce soit obligatoire ni identique d'une vidéo à l'autre.

RÈGLES D'ÉCRITURE ORALE (le texte sera LU À VOIX HAUTE par une synthèse vocale) :
- Jamais de plages ou scores avec tiret : écris "2 à 1", "de 10 à 15" — jamais "2-1" ni "10-15"
- Aucun sigle ni abréviation non lexicalisé, "contre" au lieu de "vs"
- Noms de villes et institutions en toutes lettres, jamais d'acronymes non expliqués

Pour photo_query : décris en anglais LA SCÈNE PRÉCISE qu'on devrait voir à l'écran pour ce sujet (3-6 mots, lieu/objet/action CONCRETS et photographiables), idéalement des lieux emblématiques français quand pertinent :
- ✅ "french national assembly building", "paris street protest crowd", "french countryside village aerial", "french stock exchange paris"
- ❌ concepts abstraits ("economy", "tension"), noms de personnes, mots génériques ("news")
Pour keywords_photo : 3 mots-clés anglais de repli, du plus spécifique au plus général.

Réponds UNIQUEMENT avec ce JSON (sans markdown, sans backticks) :
{{
  "news": [
    {{
      "titre": "Titre court percutant (max 8 mots)",
      "region": "Ville/région principale concernée (ex: \\"Paris\\", \\"Marseille\\") ou \\"National\\" si aucune région unique ne domine",
      "transition": "Accroche orale contextuelle avant ce sujet (2-6 mots + virgule)",
      "resume": "Résumé oral autonome 45-60 mots (première phrase = le sujet nommé)",
      "source": "Nom du média",
      "categorie": "politique|economie|science|technologie|sport|culture|environnement|societe|monde",
      "photo_query": "scène précise en anglais 3-6 mots",
      "keywords_photo": ["mot_anglais1", "mot_anglais2", "mot_anglais3"]
    }}
  ],
  "intro": "Accroche directe SANS cérémonie, 10-14 mots, qui annonce qu'on fait le tour de l'actu française du jour (ex: 'Voici l'actualité en France de ce {today}, en trois minutes.')",
  "outro": "Clôture avec rendez-vous quotidien, 8-12 mots (ex: 'C'était l'actu France du jour. On se retrouve demain.')",
  "titre_video": "Titre YouTube au format des chaînes d'actu : 'Sujet 1, sujet 2, sujet 3… L'actu France du jour ({today})' — max 95 caractères, sujets en 1-3 mots chacun",
  "hashtags": ["france", "5 à 8 hashtags français SANS le symbole #"]
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
                        print(f"  ✅ {len(result['news'])} segments France via Groq ({model})")
                        return result
            except Exception as e:
                print(f"  ⚠️  Groq erreur ({model}, essai {attempt}) : {e}")
    return None


def get_france_news(config: dict) -> dict:
    """Pipeline de collecte de l'édition Spécial France."""
    print("\n🇫🇷 ÉTAPE 1 — Collecte Spécial Actualité France...")
    n = config["TOP_N"]

    raw = fetch_france_rss(n * 3)

    if config["GROQ_API_KEY"]:
        print("  🤖 Structuration France via Groq...")
        result = structure_france_with_groq(raw, config["GROQ_API_KEY"], n)
        if result and len(result.get("news", [])) >= 3:
            news = result["news"][:n]
            result["news"] = news
            print(f"\n📋 Émission du jour ({len(news)} segments) :")
            for i, item in enumerate(news, 1):
                print(f"  {i:2}. [{item.get('source','?')}] {item['titre'][:65]}")
            return result

    # Fallback : RSS brut France sans IA
    print("  ⚠️  Groq non disponible → RSS France brut (qualité réduite)")
    if raw:
        news = []
        for a in raw[:n]:
            words = [w for w in a["titre_brut"].split() if len(w) > 4][:3]
            news.append({
                "titre":          a["titre_brut"][:80],
                "region":         "National",
                "resume":         a["desc_brute"][:200],
                "source":         a["source"],
                "categorie":      "societe",
                "keywords_photo": words or ["france", "french flag"],
            })
        return {
            "news":  news,
            "intro": f"Voici l'actualité en France de ce {date_fr(datetime.now())}, en trois minutes.",
            "outro": "C'était l'actu France du jour. On se retrouve demain.",
            "titre_video": f"🇫🇷 L'actu France du jour — {date_fr(datetime.now(), with_weekday=False)}",
            "hashtags": ["france", "actualité", "francais", "national", "info"],
        }

    # Démo statique (aucune source disponible)
    print("  ⚠️  Aucune source disponible → segments de démo")
    return _demo_france(config["TOP_N"])


def _demo_france(n: int) -> dict:
    topics = [
        ("Réforme votée à l'Assemblée nationale", "Paris", "Premier sujet ce jour, une décision qui va marquer le pays,",
         "L'Assemblée nationale a adopté hier soir un texte de loi très attendu, après plusieurs jours de débats houleux entre les groupes parlementaires. Le gouvernement salue une avancée majeure.",
         "Le Figaro France", "politique", ["french national assembly", "paris government building", "politics"]),
        ("Grève nationale dans les transports", "National", "Autre sujet qui touche le quotidien des Français,",
         "Un mouvement de grève perturbe fortement les transports en commun dans plusieurs grandes villes françaises. Les syndicats réclament de meilleures conditions de travail et de nouvelles négociations salariales.",
         "France Info", "societe", ["french train station crowd", "public transport strike", "commuters"]),
        ("Nouvelle usine créée dans l'Ouest", "Rennes", "Du côté de l'économie française,",
         "Une entreprise française annonce la création de plusieurs centaines d'emplois avec l'ouverture d'une nouvelle usine dans l'Ouest du pays. Un investissement salué par les élus locaux.",
         "Ouest-France", "economie", ["french factory industrial", "manufacturing plant france", "industry"]),
        ("Vague de chaleur sur le pays", "National", "Toujours en France, du côté de la météo,",
         "Météo-France place plusieurs départements en vigilance orange pour une vague de chaleur inhabituelle. Les autorités appellent à la prudence, notamment pour les personnes âgées et les enfants.",
         "France Bleu", "environnement", ["french countryside heatwave", "sun summer france", "weather"]),
        ("Un film français récompensé à l'international", "France", "Et pour terminer sur une note plus légère,",
         "Un film français vient de remporter une distinction majeure dans un festival international, saluant le savoir-faire du cinéma tricolore devant la presse spécialisée du monde entier.",
         "Le Parisien", "culture", ["cinema film award", "french cinema paris", "movie premiere"]),
    ]
    news = [{"titre": t[0], "region": t[1], "transition": t[2], "resume": t[3], "source": t[4],
             "categorie": t[5], "keywords_photo": t[6]} for t in topics[:n]]
    return {
        "news":  news,
        "intro": "Bienvenue dans votre Spécial France, l'actualité du pays en trois minutes.",
        "outro": "C'était l'actu France du jour. On se retrouve demain.",
        "titre_video": f"🇫🇷 L'actu France du jour — {date_fr(datetime.now(), with_weekday=False)}",
        "hashtags": ["france", "actualité", "francais", "national", "info"],
    }
