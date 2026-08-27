"""
top3.py — Édition spéciale TOP 3 DE L'ACTU (format compte à rebours).

Contrairement au journal classique (5 sujets traités à plat), ce format
sélectionne les 3 actualités les plus MARQUANTES du jour (impact, ampleur,
surprise — pas seulement la plus recoupée par les sources) et les présente
en compte à rebours : n°3 → n°2 → n°1, comme un classement, pour créer un
effet de suspense qui retient jusqu'à la fin de la vidéo.

Réutilise le même pool RSS que le journal principal (news.py) — seule la
sélection/structuration Groq et le rendu visuel (numéro géant, voir
render.py) changent. Le JSON produit garde le même schéma que news.py
(+ un champ "rang" par sujet : 3, 2 puis 1, dans l'ordre de la liste)
pour que tout le reste du pipeline (photos, audio, métadonnées) fonctionne
sans modification.
"""
import re
import json
from datetime import datetime

import requests

from .config import date_fr
from .news import fetch_rss_raw, GROQ_MODELS, _fmt_age_fr


def structure_top3_with_groq(articles: list[dict], api_key: str) -> dict | None:
    """Structure les articles en TOP 3 compte à rebours via Groq."""
    if not api_key:
        return None

    today = date_fr(datetime.now(), with_weekday=False)
    articles_txt = "\n".join(
        f"{i+1}. [{a['source']}, {_fmt_age_fr(a.get('age_heures'))}] {a['titre_brut']} — {a['desc_brute'][:150]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Tu es le rédacteur en chef d'un média d'actualité nouvelle génération sur YouTube et TikTok, dans l'esprit des chaînes d'info les plus vues. Ton public a 15-35 ans. Nous sommes le {today}.

Voici {len(articles)} articles RSS bruts, avec leur ancienneté indiquée entre crochets :
{articles_txt}

IMPORTANT sur la fraîcheur : préfère toujours un article récent ("il y a moins d'1h", "il y a Xh") à un article plus ancien ("il y a Xj") qui parle du MÊME sujet. Si un sujet n'existe QUE dans des articles vieux de plusieurs jours et qu'aucun article récent ne le confirme comme toujours d'actualité aujourd'hui, ne le retiens PAS.

Tu dois construire un TOP 3 EN COMPTE À REBOURS, format vidéo très populaire sur les réseaux : 3 actualités classées de la moins marquante à la PLUS marquante de la journée. Choisis les 3 actualités les plus IMPACTANTES ou SURPRENANTES du jour (quel que soit le thème : politique, catastrophe, buzz culturel, sport, économie, science, fait insolite...) — pas forcément les plus recoupées par les sources, mais celles qui ont le plus grand retentissement, le plus grand effet de surprise, ou les conséquences les plus importantes.
- Place en 3ème position (rang 3, EN PREMIER dans ta liste JSON) l'actualité marquante mais la moins spectaculaire des trois.
- Place en 2ème position (rang 2, DEUXIÈME dans la liste) une actualité plus forte encore.
- Place en 1ère position (rang 1, DERNIÈRE dans la liste — le clou du classement) LA actualité la plus marquante, la plus grosse ou la plus inattendue de la journée. C'est l'apex de la vidéo : elle doit justifier à elle seule qu'on regarde jusqu'au bout.
- N'aie AUCUN sujet de prédilection fixe : le choix doit changer chaque jour selon ce qui domine réellement l'actualité de {today}.

Réécris chaque résumé POUR L'OREILLE : il sera lu par une voix off SANS le titre (le titre n'apparaît qu'à l'écran). Règles impératives :
- Le résumé doit être 100% autonome à l'oral : la PREMIÈRE phrase nomme clairement le sujet (pays, personne, institution).
- 2 phrases courtes sujet-verbe-complément, 35-45 mots MAXIMUM — plus court et plus punchy qu'un journal classique, on va droit au fait marquant.
- TON dynamique et accrocheur mais toujours factuel et neutre, zéro opinion, zéro sensationnalisme trompeur : le "wow" vient du FAIT lui-même, pas d'une exagération.
- Vocabulaire courant, zéro jargon. Si un terme technique est indispensable, explique-le en quelques mots dans la foulée.
- Interdits : style télégraphique, phrases nominales, débuter par un pronom ("Il", "Elle", "Ils") ou une référence vague ("Cette décision...").

Pour transition : écris l'annonce ORALE de classement que le présentateur dit juste avant le résumé, dans l'esprit d'un compte à rebours (varie la formulation d'un jour à l'autre, jamais mot pour mot identique) :
- Rang 3 : ex. "On démarre ce classement avec, en troisième place,"
- Rang 2 : ex. "En deuxième position aujourd'hui,"
- Rang 1 : ex. "Et la place numéro 1 de ce {today} revient à,"
Toujours terminer par une virgule (la voix enchaîne directement sur le résumé).

RÈGLES D'ÉCRITURE ORALE (le texte sera LU À VOIX HAUTE par une synthèse vocale) :
- Jamais de plages ou scores avec tiret : écris "2 à 1", "de 10 à 15" — jamais "2-1" ni "10-15"
- Noms de pays et d'institutions en toutes lettres : "République démocratique du Congo" (jamais "RD Congo"), "États-Unis" (jamais "USA")
- Aucun sigle ni abréviation non lexicalisé, "contre" au lieu de "vs"

Pour photo_query : décris en anglais LA SCÈNE PRÉCISE qu'on devrait voir à l'écran pour ce sujet (3-6 mots, lieu/objet/action CONCRETS et photographiables) :
- ✅ "european parliament chamber interior", "container ship port cranes", "wildfire smoke forest aerial", "stock exchange trading screens"
- ❌ concepts abstraits ("economy", "tension"), noms de personnes, mots génériques ("news")
Pour keywords_photo : 3 mots-clés anglais de repli, du plus spécifique au plus général.

Réponds UNIQUEMENT avec ce JSON (sans markdown, sans backticks), la liste "news" contenant EXACTEMENT 3 éléments dans l'ordre rang 3, rang 2, rang 1 :
{{
  "news": [
    {{
      "rang": 3,
      "titre": "Titre court percutant (max 8 mots)",
      "pays": "Pays principal concerné (ex: \\"France\\", \\"États-Unis\\") ou \\"International\\"",
      "transition": "Annonce orale de classement, style compte à rebours (voir consignes)",
      "resume": "Résumé oral autonome 35-45 mots (première phrase = le sujet nommé)",
      "source": "Nom du média",
      "categorie": "politique|economie|science|technologie|sport|culture|environnement|societe|monde",
      "photo_query": "scène précise en anglais 3-6 mots",
      "keywords_photo": ["mot_anglais1", "mot_anglais2", "mot_anglais3"]
    }}
  ],
  "intro": "Accroche directe et rythmée, 10-16 mots, qui annonce le concept de classement (ex: 'Voici le Top 3 des actus qui ont marqué ce {today}. On commence par la 3e place.')",
  "outro": "Clôture qui invite à réagir en commentaire sur le classement, 8-12 mots MAXIMUM (ex: 'C'était le Top 3 du jour. Dis-nous ton classement en commentaire !')",
  "titre_video": "Titre YouTube accrocheur format 'TOP 3 : sujet 1, sujet 2, sujet 3 ({today})' — max 95 caractères",
  "hashtags": ["top3", "classement", "5 à 7 hashtags français SANS le symbole #"]
}}"""

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for model in GROQ_MODELS:
        for attempt in (1, 2):
            body = {
                "model": model,
                "max_tokens": 2000,
                "temperature": 0.5,
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
                    break
                raw = r.json()["choices"][0]["message"]["content"].strip()
                raw = re.sub(r"```json\s*|\s*```", "", raw).strip()
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                    news = result.get("news", [])
                    if len(news) >= 3:
                        # Sécurité : force l'ordre/valeurs de "rang" même si le
                        # modèle s'est trompé — l'ordre de LISTE fait foi
                        # (3ème position parlée en premier, 1ère en dernier).
                        news = news[:3]
                        for i, item in enumerate(news):
                            item["rang"] = 3 - i
                        result["news"] = news
                        print(f"  ✅ TOP 3 structuré via Groq ({model})")
                        return result
            except Exception as e:
                print(f"  ⚠️  Groq erreur ({model}, essai {attempt}) : {e}")
    return None


def get_top3_news(config: dict) -> dict:
    """Pipeline de collecte de l'édition TOP 3 (compte à rebours)."""
    print("\n🏆 ÉTAPE 1 — Collecte TOP 3 de l'actu du jour...")

    # On scanne plus large que pour un journal 5 sujets (18 articles) car
    # on cherche les 3 sujets les plus MARQUANTS parmi un pool plus riche,
    # pas juste les 3 premiers dans l'ordre RSS.
    raw_articles = fetch_rss_raw(18)

    if config["GROQ_API_KEY"]:
        print("  🤖 Structuration TOP 3 via Groq (Llama 3.3)...")
        result = structure_top3_with_groq(raw_articles, config["GROQ_API_KEY"])
        if result and len(result.get("news", [])) >= 3:
            print("\n📋 Classement du jour :")
            for item in result["news"]:
                print(f"  #{item.get('rang', '?')} [{item.get('source', '?')}] {item['titre'][:60]}")
            return result

    # Fallback : RSS brut sans IA — on prend les 3 articles les plus
    # récents du pool comme approximation faute de mieux, dans l'ordre
    # inverse (le plus "gros" en dernier, arbitrairement le 1er de la liste RSS).
    print("  ⚠️  Groq non disponible → RSS brut (qualité réduite)")
    if raw_articles:
        picked = raw_articles[:3]
        news = []
        for i, a in enumerate(reversed(picked)):
            words = [w for w in a["titre_brut"].split() if len(w) > 4][:3]
            news.append({
                "titre":          a["titre_brut"][:80],
                "rang":           3 - i,
                "pays":           "International",
                "resume":         a["desc_brute"][:200],
                "source":         a["source"],
                "categorie":      "monde",
                "keywords_photo": words or ["world", "news"],
            })
        date_str = date_fr(datetime.now())
        return {
            "news":  news,
            "intro": f"Voici le Top 3 des actus qui ont marqué ce {date_str}. On commence par la 3e place.",
            "outro": "C'était le Top 3 du jour. Dis-nous ton classement en commentaire !",
            "titre_video": f"TOP 3 des actus du jour ({date_fr(datetime.now(), with_weekday=False)})",
            "hashtags": ["top3", "classement", "actualités", "news", "viral"],
        }

    print("  ⚠️  Aucune source disponible → TOP 3 de démo")
    return _demo_top3()


def _demo_top3() -> dict:
    topics = [
        (3, "Grève surprise dans les transports", "National",
         "On démarre ce classement avec, en troisième place,",
         "Un mouvement de grève inattendu paralyse les transports dans plusieurs grandes villes ce matin. Les usagers sont invités à anticiper de fortes perturbations toute la journée.",
         "France Info", "societe", ["train station crowd", "public transport strike"]),
        (2, "Percée majeure en intelligence artificielle", "International",
         "En deuxième position aujourd'hui,",
         "Des chercheurs annoncent une avancée spectaculaire en intelligence artificielle générale, capable de résoudre des problèmes jusque-là jugés hors de portée des machines.",
         "MIT Tech", "technologie", ["artificial intelligence lab", "robot research"]),
        (1, "Sommet international sur le climat", "International",
         "Et la place numéro 1 aujourd'hui revient à,",
         "Les dirigeants mondiaux se réunissent en urgence pour un sommet climatique historique, avec des engagements chiffrés jamais atteints jusqu'ici selon plusieurs délégations présentes.",
         "ONU", "environnement", ["climate summit stage", "world leaders meeting"]),
    ]
    news = [{"rang": t[0], "titre": t[1], "pays": t[2], "transition": t[3],
             "resume": t[4], "source": t[5], "categorie": t[6], "keywords_photo": t[7]}
            for t in topics]
    return {
        "news":  news,
        "intro": "Voici le Top 3 des actus qui ont marqué la journée. On commence par la 3e place.",
        "outro": "C'était le Top 3 du jour. Dis-nous ton classement en commentaire !",
        "titre_video": f"TOP 3 des actus du jour ({date_fr(datetime.now(), with_weekday=False)})",
        "hashtags": ["top3", "classement", "actualités", "news", "viral"],
    }
