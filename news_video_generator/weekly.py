"""
weekly.py — Édition RÉCAP HEBDO : vidéo YouTube LONGUE (pas un Short,
format PAYSAGE 16:9) qui regroupe tous les évènements marquants de
France survenus dans les 7 derniers jours.

Contrairement au journal quotidien (5 actus, format court vertical) ou
à Zoom Sur (1 sujet détaillé par vidéo), ce module :
- scrape les flux RSS France sur une fenêtre de 7 jours (au lieu des 48h
  du journal quotidien — voir WEEKLY_MAX_AGE_HOURS)
- envoie l'ensemble à Groq en UN seul appel pour construire un récap
  complet, aussi long que la semaine le justifie réellement (8 à 20
  segments), dédupliqué (une grève qui dure 4 jours = 1 seul segment,
  pas 4) et ordonné chronologiquement
- produit une vidéo au format PAYSAGE (16:9) : CONFIG["FORMAT"] =
  "landscape" bascule tout le pipeline de rendu (voir __init__.py,
  video.py, render.py, photos.py, subtitles.py) sans toucher au
  pipeline Shorts existant.

Le JSON produit garde le même schéma "news" que les autres modules →
photos/audio/vidéo/métadonnées sont réutilisés tels quels.
"""
import re
import json
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from .config import date_fr
from .news import _fetch_one_feed, GROQ_MODELS, _fmt_age_fr
from .france import FR_RSS_FEEDS
from .topics import _topic_keywords

# Fenêtre de fraîcheur élargie à 7 jours (le journal quotidien filtre à
# 48h — voir RSS_MAX_AGE_HOURS dans news.py) : un récap hebdo doit
# couvrir toute la semaine, pas seulement les 2 derniers jours.
WEEKLY_MAX_AGE_HOURS = 24 * 7

WEEKLY_MIN_SEGMENTS = 8
WEEKLY_MAX_SEGMENTS = 20

# Log de debug persistant : les logs console des runners GitHub Actions
# ne sont pas toujours accessibles pour le diagnostic à distance — ce
# fichier est écrit dans output/ et inclus dans la release pour pouvoir
# être inspecté après coup en cas de fallback inattendu vers la démo.
_debug_lines: list[str] = []


def _dbg(msg: str):
    _debug_lines.append(msg)
    print(msg)


def _write_debug_log(config: dict):
    try:
        path = Path(config.get("OUTPUT_DIR", "./output")) / "weekly_debug.log"
        path.write_text("\n".join(_debug_lines), encoding="utf-8")
    except Exception:
        pass


def fetch_weekly_france_pool(per_feed: int = 12) -> list[dict]:
    """Scrape les flux France sur 7 jours (plus d'articles par source que
    le journal quotidien, fenêtre de fraîcheur élargie à WEEKLY_MAX_AGE_HOURS).
    `per_feed` volontairement modéré (12, pas 20+) : au-delà, le prompt
    Groq grossit inutilement et augmente le risque de réponse tronquée."""
    print("  🇫🇷 Scraping RSS France (fenêtre 7 jours)...")
    per_source: dict[str, list[dict]] = {}
    with ThreadPoolExecutor(max_workers=len(FR_RSS_FEEDS)) as ex:
        futures = {
            ex.submit(_fetch_one_feed, s, u, per_feed, WEEKLY_MAX_AGE_HOURS): s
            for s, u in FR_RSS_FEEDS
        }
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
    _dbg(f"  ✅ {len(results)} articles collectés sur 7 jours ({ok}/{len(FR_RSS_FEEDS)} sources OK)")
    for s, arts in per_source.items():
        _dbg(f"    · {s} : {len(arts)} article(s)")
    return results


def _dedupe_weekly_segments(news: list[dict]) -> list[dict]:
    """Garde-fou anti-doublon (même logique que topics.py) : si Groq a
    quand même généré deux segments qui se recoupent trop (ex: un même
    évènement raconté deux fois à des jours différents), on ne garde
    que le premier plutôt que de dupliquer le récap."""
    merged: list[dict] = []
    for item in news:
        kw = _topic_keywords(item.get("titre", ""))
        is_dup = False
        for m in merged:
            mkw = _topic_keywords(m.get("titre", ""))
            if not kw or not mkw:
                continue
            overlap = len(kw & mkw) / max(1, min(len(kw), len(mkw)))
            if overlap >= 0.6:
                is_dup = True
                break
        if not is_dup:
            merged.append(item)
    return merged


def structure_weekly_with_groq(articles: list[dict], api_key: str) -> dict | None:
    """Construit le récap hebdomadaire complet en UN appel Groq : autant
    de segments que la semaine le justifie réellement (entre 8 et 20)."""
    if not api_key:
        return None

    # Cap défensif : au-delà d'une centaine d'articles, le prompt devient
    # inutilement long sans vraiment améliorer le récap (Groq doit de
    # toute façon dédupliquer/résumer) — et ça augmente le risque de
    # réponse tronquée. On garde les plus récents en priorité.
    if len(articles) > 100:
        articles = sorted(articles, key=lambda a: a.get("age_heures") or 999)[:100]

    today = date_fr(datetime.now())
    articles_txt = "\n".join(
        f"{i+1}. [{a['source']}, {_fmt_age_fr(a.get('age_heures'))}] {a['titre_brut']} — {a['desc_brute'][:120]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""Tu es rédacteur en chef d'une émission hebdomadaire YouTube "Récap de la semaine" consacrée à l'actualité FRANÇAISE. Nous sommes le {today}, tu couvres les 7 derniers jours.

Voici {len(articles)} articles RSS français des 7 derniers jours, avec leur ancienneté entre crochets :
{articles_txt}

Construis un récap COMPLET et DÉTAILLÉ de la semaine écoulée en France :
- Identifie TOUS les évènements/sujets réellement marquants de la semaine (politique nationale, société, économie, faits divers majeurs, régions, culture...) — ne te limite PAS à un nombre fixe : génère entre 8 et 20 segments selon ce que la semaine a RÉELLEMENT produit (une semaine calme = moins de segments, une semaine chargée = plus).
- DÉDUPLIQUE : si plusieurs articles couvrent le même évènement à des jours différents (ex: une grève qui dure plusieurs jours), n'en fais qu'UN SEUL segment qui raconte l'évolution complète sur la semaine, jamais un segment par article.
- ORDONNE par ordre chronologique (du plus ancien au plus récent dans la semaine), sauf si un regroupement thématique est plus clair pour un sujet qui a duré toute la semaine.
- Pour chaque segment, précise le fait principal ET son évolution/contexte sur la semaine si pertinent.

Résumés 50-80 mots par segment, 100% autonomes à l'oral (voix off SANS le titre affiché) :
- La PREMIÈRE phrase nomme clairement le sujet (lieu, personne, institution).
- Phrases courtes sujet-verbe-complément, factuel, neutre, aucune opinion.
- Interdits : style télégraphique, débuter par un pronom vague.

Pour transition : accroche orale (2-6 mots + virgule) cohérente avec l'enchaînement chronologique/thématique — jamais "On commence"/"On continue" répété mécaniquement.

RÈGLES D'ÉCRITURE ORALE :
- Scores/plages toujours avec "à" : "2 à 1" — jamais de tiret
- Pays/institutions en toutes lettres, aucun sigle non lexicalisé, "contre" au lieu de "vs"

Pour photo_query : scène anglaise précise et photographiable (3-6 mots) liée SPÉCIFIQUEMENT à ce segment.
Pour keywords_photo : 3 mots-clés anglais de repli.

Réponds UNIQUEMENT avec ce JSON (sans markdown, sans backticks) :
{{
  "news": [
    {{
      "titre": "Titre court percutant (max 8 mots)",
      "transition": "Accroche orale (2-6 mots + virgule)",
      "resume": "Résumé oral autonome 50-80 mots",
      "source": "Nom du média principal (ou 'Sources multiples')",
      "categorie": "politique|economie|science|technologie|sport|culture|environnement|societe|monde",
      "photo_query": "scène précise en anglais 3-6 mots",
      "keywords_photo": ["mot1", "mot2", "mot3"]
    }}
  ],
  "intro": "Accroche d'ouverture du récap hebdo, 15-20 mots (ex: 'Cette semaine en France, voici tout ce qu'il fallait retenir, en un seul récap.')",
  "outro": "Clôture donnant rendez-vous la semaine prochaine, 10-15 mots",
  "titre_video": "Titre YouTube accrocheur pour un récap hebdo (max 95 caractères, avec la période couverte)",
  "hashtags": ["recaphebdo", "5 à 8 hashtags français SANS le symbole #"]
}}"""

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    _dbg(f"    ℹ️  Prompt : {len(articles)} articles envoyés à Groq")

    for model in GROQ_MODELS:
        for attempt in (1, 2):
            body = {
                "model": model,
                "max_tokens": 7000,
                "temperature": 0.4,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "user", "content": prompt}],
            }
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers=headers, json=body, timeout=90
                )
                if r.status_code == 429:
                    _dbg(f"  ⚠️  Groq 429 rate-limit ({model}, essai {attempt})")
                    import time as _t; _t.sleep(3 * attempt)
                    continue
                if r.status_code != 200:
                    _dbg(f"  ⚠️  Groq HTTP {r.status_code} ({model}) : {r.text[:500]}")
                    break
                resp_json = r.json()
                raw_full = resp_json["choices"][0]["message"]["content"].strip()
                finish_reason = resp_json["choices"][0].get("finish_reason", "?")
                usage = resp_json.get("usage", {})
                _dbg(f"    ℹ️  Réponse Groq ({model}) : finish_reason={finish_reason}, "
                     f"tokens={usage.get('completion_tokens','?')}/{usage.get('total_tokens','?')}, "
                     f"{len(raw_full)} caractères")
                raw = re.sub(r"```json\s*|\s*```", "", raw_full).strip()
                match = re.search(r'\{.*\}', raw, re.DOTALL)
                if not match:
                    _dbg(f"  ⚠️  Aucun JSON exploitable dans la réponse. Extrait : {raw[:400]!r}")
                    continue
                try:
                    result = json.loads(match.group(0))
                except json.JSONDecodeError as je:
                    _dbg(f"  ⚠️  JSON invalide ({je}). Fin de la réponse : {raw[-300:]!r}")
                    continue
                if result.get("news"):
                    nb_avant = len(result["news"])
                    result["news"] = _dedupe_weekly_segments(result["news"])
                    _dbg(f"  ✅ {nb_avant} segments générés, {len(result['news'])} après dédoublonnage ({model})")
                    return result
                _dbg(f"  ⚠️  JSON valide mais champ 'news' vide/absent ({model}). Clés reçues : {list(result.keys())}")
            except Exception as e:
                _dbg(f"  ⚠️  Groq erreur ({model}, essai {attempt}) : {type(e).__name__}: {e}")
    return None


def get_weekly_france_news(config: dict) -> dict:
    """Pipeline de collecte du récap hebdomadaire France."""
    _debug_lines.clear()
    _dbg("\n📅 ÉTAPE 1 — Collecte du récap hebdomadaire France (7 jours)...")

    pool = fetch_weekly_france_pool()

    if not config["GROQ_API_KEY"]:
        _dbg("  ⚠️  Pas de clé Groq → récap de démo")
        _write_debug_log(config)
        return _demo_weekly()
    if not pool:
        _dbg("  ⚠️  Aucun article RSS collecté sur 7 jours → récap de démo")
        _write_debug_log(config)
        return _demo_weekly()

    _dbg("  🤖 Structuration du récap via Groq...")
    result = structure_weekly_with_groq(pool, config["GROQ_API_KEY"])
    if result and len(result.get("news", [])) >= 3:
        news = result["news"][:WEEKLY_MAX_SEGMENTS]
        result["news"] = news
        _dbg(f"\n📋 Récap de la semaine ({len(news)} segments) :")
        for i, item in enumerate(news, 1):
            _dbg(f"  {i:2}. [{item.get('source','?')}] {item['titre'][:65]}")
        _write_debug_log(config)
        return result

    _dbg(f"  ⚠️  Structuration Groq échouée ou insuffisante "
         f"({len(result.get('news', [])) if result else 0} segments) → récap de démo")
    _write_debug_log(config)
    return _demo_weekly()


def _demo_weekly() -> dict:
    """Récap de démo statique (aucune source disponible)."""
    today = date_fr(datetime.now())
    topics = [
        ("Ouverture du procès très attendu à Paris", "Premier retour sur une semaine chargée,",
         "Le procès très suivi qui s'est ouvert lundi à Paris a marqué le début de semaine, avec une forte présence médiatique et des débats qui devraient s'étendre sur plusieurs jours devant la cour.",
         "Sources multiples", "societe", ["french courthouse paris", "justice building", "trial"]),
        ("Grève reconduite dans les transports", "Autre sujet qui a rythmé la semaine,",
         "Le mouvement de grève dans les transports, débuté en milieu de semaine, a été reconduit après l'échec des négociations avec le gouvernement. Plusieurs villes ont été fortement impactées.",
         "Sources multiples", "societe", ["french train station", "public transport strike", "commuters"]),
        ("Nouvelle usine annoncée dans le Nord", "Du côté de l'économie cette semaine,",
         "Une entreprise industrielle a confirmé jeudi la création de plusieurs centaines d'emplois dans le Nord de la France, saluée par les élus locaux et les syndicats.",
         "Sources multiples", "economie", ["french factory industrial", "manufacturing plant france", "industry"]),
        ("Épisode de canicule sur une grande partie du pays", "Toujours cette semaine, côté météo,",
         "Météo-France a placé plusieurs départements en vigilance orange durant le week-end, avec des températures largement supérieures aux normales de saison sur une bonne partie du territoire.",
         "Sources multiples", "environnement", ["french countryside heatwave", "sun summer france", "weather"]),
        ("Une victoire sportive qui a marqué les esprits", "Et pour clore cette semaine sur une note positive,",
         "Le sport français a connu un moment fort samedi, largement commenté sur les réseaux sociaux et salué par plusieurs personnalités politiques au cours du week-end.",
         "Sources multiples", "sport", ["french athlete celebration", "sports victory france", "stadium"]),
    ]
    news = [{"titre": t[0], "transition": t[1], "resume": t[2], "source": t[3],
             "categorie": t[4], "keywords_photo": t[5]} for t in topics]
    return {
        "news":  news,
        "intro": "Cette semaine en France, voici tout ce qu'il fallait retenir, en un seul récap complet.",
        "outro": "C'était le récap de la semaine. Rendez-vous samedi prochain pour la suite.",
        "titre_video": f"📅 Récap de la semaine en France — {today}",
        "hashtags": ["recaphebdo", "france", "actualite", "semaine", "récap"],
    }
