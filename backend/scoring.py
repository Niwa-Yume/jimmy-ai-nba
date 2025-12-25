"""
Module de scoring pour identifier les "Jimmy Locks" (Paris haute confiance).
"""

def calculate_confidence_score(projection_data, market_line, game_spread=0):
    """
    Calcule un score de 0 à 100 pour la qualité du pari.
    """
    score = 50.0  # Base neutre

    # [cite_start]1. Analyse de l'EDGE (Marge) [cite: 1]
    # Plus la projection est loin de la ligne, mieux c'est.
    if market_line <= 0: return 0, "N/A"

    proj = projection_data['projection']
    # Calcul en pourcentage d'écart
    edge_percent = (proj - market_line) / market_line

    # Bonus pour l'Edge (Max +20 pts)
    if abs(edge_percent) > 0.15: score += 15
    elif abs(edge_percent) > 0.10: score += 15
    elif abs(edge_percent) > 0.05: score += 10
    else: score -= 5 # Marge trop faible

    # [cite_start]2. Analyse de la CONSISTANCE (Régularité) [cite: 1]
    # CV = Ecart-type / Moyenne
    consistency = projection_data.get('consistency', 10)
    mean_val = projection_data.get('recent_avg', proj)

    if mean_val > 0:
        cv = consistency / mean_val
        if cv < 0.15: score += 15       # Très régulier (ex: LeBron)
        elif cv < 0.20: score += 10
        elif cv > 0.35: score -= 10     # Très instable (ex: Poole) -> Disqualification quasi auto
        elif cv > 0.25: score -= 5

    # [cite_start]3. Défense (DvP - Defense vs Position) [cite: 1]
    # Le facteur défensif vient de defense_ratings.py
    def_factor = projection_data.get('defensive_factor', 1.0)

    if def_factor >= 1.08: score += 15   # Matchup favorable (Zone verte)
    elif def_factor <= 0.92: score -= 10 # Matchup horrible (Zone rouge)

    # 4. Risque de Blowout (Game Script)
    # Si le match est déséquilibré (>14 pts d'écart prévu), les stars jouent moins.
    if abs(game_spread) >= 14:
        score -= 15  # PÉNALITÉ MAJEURE : Risque de "bench" au 4e quart-temps
    elif abs(game_spread) >= 10:
        score -= 5

    # CLASSIFICATION FINALE
    tag = "PASS"
    if score >= 80: tag = "🔒 LOCK"
    elif score >= 65: tag = "✅ PLAY"
    elif score >= 50: tag = "⚠️ LEAN"

    return round(score, 1), tag