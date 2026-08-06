"""
monthly.py — Édition RÉCAP MENSUEL : vidéo YouTube LONGUE (format paysage
16:9) qui regroupe les évènements marquants de France sur un mois calendaire
complet.

Contrairement au récap hebdo (weekly.py), qui scrape les flux RSS en direct
sur une fenêtre de 7 jours, un récap mensuel porte sur un mois déjà terminé :
les flux RSS ne conservent pas un mois complet d'historique (souvent
quelques jours à deux semaines selon les sources), donc un scraping RSS+Groq
classique ne peut PAS reconstituer un mois entier de façon fiable.

Ce module charge à la place un script déjà rédigé et vérifié (recherché
manuellement / via Claude à partir de sources fiables, un mois donné = un
fichier) plutôt que de tenter un scraping impossible. Le JSON suit
EXACTEMENT le même schéma que la sortie Groq du récap hebdo (voir
weekly.py) : photos, audio, vidéo et métadonnées sont donc réutilisés tels
quels, sans aucune modification du reste du pipeline.

Pour ajouter un nouveau mois : déposer un fichier
`data/recap_<AAAA>_<MM>.json` (même schéma que recap_2026_07.json) et
lancer `python3 run_pipeline.py --theme monthly --recap-period AAAA_MM`
(ou laisser vide pour prendre automatiquement le mois précédent).
"""
import json
from pathlib import Path
from datetime import datetime, timedelta

_DATA_DIR = Path(__file__).parent / "data"


def default_period() -> str:
    """Mois précédent au format AAAA_MM (ex: exécuté en août 2026 → '2026_07').
    Utilisé quand CONFIG['RECAP_PERIOD'] n'est pas fourni explicitement."""
    first_of_this_month = datetime.now().replace(day=1)
    last_month = first_of_this_month - timedelta(days=1)
    return last_month.strftime("%Y_%m")


def get_monthly_france_news(config: dict) -> dict:
    """Charge le script du récap mensuel depuis data/recap_<periode>.json.
    Retombe sur un récap de démo si le fichier n'existe pas encore (mois pas
    encore préparé) — ne bloque jamais le pipeline."""
    period = config.get("RECAP_PERIOD") or default_period()
    path = _DATA_DIR / f"recap_{period}.json"

    if not path.exists():
        print(f"  ⚠️  Aucun script préparé pour {period} ({path}) → récap de démo")
        return _demo_monthly(period)

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    nb = len(data.get("news", []))
    print(f"  ✅ Récap mensuel chargé : {path} ({nb} segments)")
    for i, item in enumerate(data.get("news", []), 1):
        print(f"    {i:2}. [{item.get('categorie','?')}] {item.get('titre','?')[:65]}")
    return data


def _demo_monthly(period: str) -> dict:
    """Récap de démo statique (aucun script préparé pour ce mois)."""
    try:
        annee, mois = period.split("_")
    except ValueError:
        annee, mois = str(datetime.now().year), "01"
    label = f"{mois}/{annee}"
    topics = [
        ("Un mois marqué par une vague de chaleur", "Pour commencer, le fil rouge du mois,",
         "Le mois écoulé a été marqué par des températures très supérieures aux normales de saison sur une large partie du territoire, avec plusieurs départements placés en vigilance canicule et des records locaux battus selon Météo-France.",
         "Sources multiples", "environnement", ["heatwave summer france", "sun countryside", "weather"]),
        ("Un fait politique majeur a rythmé le mois", "Sur le plan politique,",
         "Le gouvernement a fait face à un mois chargé sur le plan institutionnel, avec plusieurs textes discutés au Parlement et des tensions persistantes entre les différents groupes politiques à l'approche des prochaines échéances électorales.",
         "Sources multiples", "politique", ["french parliament building", "government", "politics"]),
        ("Un évènement sportif a marqué les esprits", "Côté sport,",
         "Le mois a été marqué par une compétition sportive majeure largement suivie par le public français, avec des performances saluées par la presse spécialisée et les personnalités politiques.",
         "Sources multiples", "sport", ["stadium sports france", "athlete", "competition"]),
    ]
    news = [{"titre": t[0], "transition": t[1], "resume": t[2], "source": t[3],
             "categorie": t[4], "keywords_photo": t[5]} for t in topics]
    return {
        "news": news,
        "intro": f"Voici le récap complet du mois de {label} : tout ce qu'il fallait retenir, en une seule vidéo.",
        "outro": "C'était le récap du mois. Rendez-vous le mois prochain pour la suite de l'actualité.",
        "titre_video": f"📅 Récap du mois — {label}",
        "hashtags": ["recapmensuel", "france", "actualite", "récap"],
    }
