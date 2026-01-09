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


def _extract_market_fields(stats_json):
    """Retourne (projection, line, odds, bookmaker, market_label) selon le marché demandé."""
    market = stats_json.get("market", "points") or "points"
    market = market.strip().lower()
    field_map = {
        "points": ("projection_points", "betting_line_points", "betting_odds_points", "points"),
        "rebounds": ("projection_rebounds", "betting_line_rebounds", "betting_odds_rebounds", "rebonds"),
        "assists": ("projection_assists", "betting_line_assists", "betting_odds_assists", "passes"),
        "three_points_made": ("projection_three_points_made", "betting_line_three_points_made", "betting_odds_three_points_made", "3pts"),
    }
    proj_key, line_key, odds_key, label = field_map.get(market, field_map["points"])
    proj = stats_json.get(proj_key, 0)
    line = stats_json.get(line_key) or 0
    odds = stats_json.get(odds_key) or None
    bookmaker = stats_json.get("betting_bookmaker") or "Bookmaker"
    return proj, line, odds, bookmaker, label, market


def _local_jimmy_rule(player_name, stats_json):
    """Fallback local qui génère un verdict court (3-4 phrases) sans appeler une API externe."""
    opponent = stats_json.get('opponent', 'N/A')
    location = stats_json.get('location', 'N/A')
    proj, line, odds, bookmaker, label, market = _extract_market_fields(stats_json)
    missing = stats_json.get('missing_stars', [])

    diff = proj - (line or 0)
    loc_str = 'à domicile' if location == 'Home' else "à l'extérieur"
    usage_note = ''
    if missing:
        usage_note = f" (boost offense: {', '.join(missing)})"

    if not line:
        # pas de ligne -> pas de verdict
        return f"Pas de ligne bookmaker disponible pour {player_name} ({label}). Projection {proj:.1f}{usage_note}."

    if diff >= 1.5:
        return f"{player_name} projeté {proj:.1f} {label} vs ligne {line} ({bookmaker}). VALUE BET : OVER probable {loc_str}{usage_note}."
    if diff <= -1.5:
        return f"{player_name} projeté {proj:.1f} {label} vs ligne {line} ({bookmaker}). OPPORTUNITÉ : UNDER possible {loc_str}."
    return f"Ligne proche ({line}) pour {player_name} — projection {proj:.1f} {label}. Pas d'action recommandée, prudence."


def ask_jimmy(player_name, stats_json):
    """
    Génère une analyse de pari en comparant notre projection à la ligne du bookmaker.
    Utilise Gemini (si dispo) ou un fallback local quand l'API n'est pas configurée.
    """
    opponent = stats_json.get('opponent', 'N/A')
    location = stats_json.get('location', 'N/A')
    defense_desc = stats_json.get('defense_description', '')

    proj, line, odds, bookmaker, label, market = _extract_market_fields(stats_json)
    missing_stars = stats_json.get('missing_stars', [])

    if client is None:
        # mode fallback local
        try:
            return _local_jimmy_rule(player_name, stats_json)
        except Exception as e:
            return f"Jimmy offline — verdict indisponible (Erreur interne: {e})"

    loc_str = "DOMICILE 🏠" if location == 'Home' else "EXTÉRIEUR ✈️"
    prompt = f"""
    Tu es "Jimmy", une IA experte en paris sportifs NBA.
    Analyse courte pour {player_name} vs {opponent} ({loc_str}).
    Marché : {label} ({market}).
    Notre projection: {proj:.1f}. Ligne: {line} ({bookmaker}) Cote Over: {odds}.
    Contexte défense: {defense_desc}.
    Indique en 3-4 phrases si c'est OVER, UNDER ou passer, en français.
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.0-flash',
            contents=prompt
        )
        return getattr(response, 'text', str(response))
    except Exception:
        return _local_jimmy_rule(player_name, stats_json)
