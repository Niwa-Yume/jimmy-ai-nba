import os
from dotenv import load_dotenv

load_dotenv()

# Chargement optionnel du client genai (Gemini)
client = None
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
    except Exception:
        client = None
else:
    # Pas d'API Key : on reste en mode fallback local
    client = None


def _local_jimmy_rule(player_name, stats_json):
    """Fallback local qui génère un verdict court (3-4 phrases) sans appeler une API externe."""
    opponent = stats_json.get('opponent', 'N/A')
    location = stats_json.get('location', 'N/A')
    proj = stats_json.get('projection_points', 0)
    line = stats_json.get('betting_line_points') or 0
    odds = stats_json.get('betting_odds_points') or None
    bookmaker = stats_json.get('betting_bookmaker') or 'Bookmaker'
    missing = stats_json.get('missing_stars', [])

    diff = proj - (line or 0)
    loc_str = 'à domicile' if location == 'Home' else 'à l\'extérieur'
    usage_note = ''
    if missing:
        usage_note = f" (boost offense: {', '.join(missing)})"

    if line == 0:
        # pas de ligne -> pas de verdict
        return f"Pas de ligne bookmaker disponible pour {player_name}. Projection {proj:.1f} pts{usage_note}."

    if diff >= 1.5:
        return f"{player_name} projeté {proj:.1f} pts vs ligne {line} ({bookmaker}). VALUE BET : OVER probable {loc_str}{usage_note}."
    if diff <= -1.5:
        return f"{player_name} projeté {proj:.1f} pts vs ligne {line} ({bookmaker}). OPPORTUNITÉ : UNDER possible {loc_str}."
    return f"Ligne proche ({line}) pour {player_name} — projection {proj:.1f}. Pas d'action recommandée, prudence."


def ask_jimmy(player_name, stats_json):
    """
    Génère une analyse de pari en comparant notre projection à la ligne du bookmaker.
    Utilise Gemini (si dispo) ou un fallback local quand l'API n'est pas configurée.
    """
    # Build prompt content (same as before but lean)
    opponent = stats_json.get('opponent', 'N/A')
    location = stats_json.get('location', 'N/A')
    defense_desc = stats_json.get('defense_description', '')
    our_projection = stats_json.get('projection_points', 0)
    bookmaker_line = stats_json.get('betting_line_points', 0)
    bookmaker_odds = stats_json.get('betting_odds_points', 1.90)
    bookmaker_name = stats_json.get('betting_bookmaker', 'Bookmaker')
    missing_stars = stats_json.get('missing_stars', [])

    if client is None:
        # mode fallback local
        try:
            return _local_jimmy_rule(player_name, stats_json)
        except Exception as e:
            return f"Jimmy offline — verdict indisponible (Erreur interne: {e})"

    # Si client disponible, tenter d'appeler le modèle
    loc_str = "DOMICILE 🏠" if location == 'Home' else "EXTÉRIEUR ✈️"
    prompt = f"""
    Tu es "Jimmy", une IA experte en paris sportifs NBA.
    Analyse courte pour {player_name} vs {opponent} ({loc_str}).
    Notre projection: {our_projection:.1f} pts. Ligne: {bookmaker_line} ({bookmaker_name}) Cote Over: {bookmaker_odds}.
    Contexte défense: {defense_desc}.
    Indique en 3-4 phrases si c'est OVER, UNDER ou passer, en français.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        # response.text contient la sortie textuelle
        return getattr(response, 'text', str(response))
    except Exception as e:
        # En cas d'erreur avec l'API, fallback local
        return _local_jimmy_rule(player_name, stats_json)
