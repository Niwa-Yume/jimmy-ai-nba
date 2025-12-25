"""
Module de gestion des ratings défensifs et du Pace des équipes NBA.

🧠 Contexte Défensif : DvP (Defense vs Position)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ce module est le cœur de l'intelligence défensive.
Il ne se contente pas de dire "Cette équipe défend bien".
Il dit : "Cette équipe défend bien contre les PIVOTS, mais mal contre les MENEURS".
"""

# Source: NBA.com Advanced Stats (Possessions per 48 minutes)
PACE_RATINGS = {
    "WAS": 1.04, "IND": 1.03, "ATL": 1.03, "SAS": 1.02, "OKC": 1.02,
    "GSW": 1.01, "UTA": 1.01, "MIL": 1.01, "SAC": 1.01, "LAL": 1.01,
    "HOU": 1.00, "TOR": 1.00, "BKN": 1.00, "MEM": 1.00, "CHI": 1.00,
    "NOP": 0.99, "PHX": 0.99, "LAC": 0.99, "BOS": 0.99, "PHI": 0.99,
    "DET": 0.98, "ORL": 0.98, "MIA": 0.98, "POR": 0.98, "DAL": 0.98,
    "MIN": 0.97, "CLE": 0.97, "DEN": 0.96, "NYK": 0.95,
}

# 🛡️ MATRICE DvP (Defense vs Position)
# Coefficient multiplicateur pour les points concédés par position.
# < 1.00 : L'équipe éteint ce poste (Zone Rouge pour l'attaquant)
# > 1.00 : L'équipe se fait trouer par ce poste (Zone Verte pour l'attaquant)
# Positions : PG (Meneur), SG (Arrière), SF (Ailier), PF (Ailier Fort), C (Pivot)

DVP_RATINGS = {
    # --- ELITE DEFENSES ---
    "MIN": {"PG": 0.92, "SG": 0.88, "SF": 0.90, "PF": 0.90, "C": 0.85}, # Gobert verrouille le C
    "BOS": {"PG": 0.90, "SG": 0.90, "SF": 0.92, "PF": 0.94, "C": 0.95}, # Holiday/White verrouillent les Guards
    "ORL": {"PG": 0.93, "SG": 0.92, "SF": 0.90, "PF": 0.91, "C": 0.94},
    "OKC": {"PG": 0.94, "SG": 0.91, "SF": 0.93, "PF": 0.90, "C": 0.88}, # Holmgren protège le cercle
    "CLE": {"PG": 0.95, "SG": 0.94, "SF": 0.96, "PF": 0.90, "C": 0.92}, # Mobley/Allen

    # --- DEFENSES MOYENNES / SPÉCIFIQUES ---
    "MIA": {"PG": 0.96, "SG": 0.98, "SF": 0.95, "PF": 0.99, "C": 0.90}, # Bam tient le C
    "LAL": {"PG": 1.05, "SG": 1.02, "SF": 1.00, "PF": 0.98, "C": 0.92}, # AD tient le C, mais les Guards souffrent
    "PHI": {"PG": 1.02, "SG": 1.00, "SF": 1.01, "PF": 1.03, "C": 0.90}, # Embiid tient le C
    "DEN": {"PG": 1.04, "SG": 1.03, "SF": 1.00, "PF": 0.98, "C": 0.96},
    "PHX": {"PG": 1.00, "SG": 1.01, "SF": 0.98, "PF": 1.02, "C": 1.03},
    "NYK": {"PG": 0.98, "SG": 0.99, "SF": 0.95, "PF": 1.00, "C": 1.02}, # Anunoby tient les Ailiers
    "MIL": {"PG": 1.06, "SG": 1.04, "SF": 0.98, "PF": 0.92, "C": 0.98}, # Giannis aide en PF, mais Lillard en PG...
    "GSW": {"PG": 1.02, "SG": 1.00, "SF": 0.98, "PF": 0.95, "C": 1.05}, # Green tient le PF, mais petits au C
    "LAC": {"PG": 1.01, "SG": 1.00, "SF": 0.96, "PF": 1.02, "C": 1.01},
    "DAL": {"PG": 1.03, "SG": 1.02, "SF": 1.00, "PF": 1.04, "C": 0.98},
    "SAC": {"PG": 1.05, "SG": 1.06, "SF": 1.04, "PF": 1.02, "C": 1.05},
    "BKN": {"PG": 1.04, "SG": 1.03, "SF": 1.02, "PF": 1.05, "C": 1.04},
    "HOU": {"PG": 0.98, "SG": 0.97, "SF": 0.96, "PF": 1.02, "C": 1.00},
    "NOP": {"PG": 1.02, "SG": 1.01, "SF": 0.98, "PF": 1.04, "C": 1.05},

    # --- PASSOIRES (CIBLES) ---
    "WAS": {"PG": 1.15, "SG": 1.14, "SF": 1.12, "PF": 1.10, "C": 1.15}, # Ciblez tout le monde
    "DET": {"PG": 1.10, "SG": 1.12, "SF": 1.08, "PF": 1.09, "C": 1.05},
    "CHA": {"PG": 1.12, "SG": 1.13, "SF": 1.10, "PF": 1.08, "C": 1.11},
    "POR": {"PG": 1.14, "SG": 1.12, "SF": 1.10, "PF": 1.08, "C": 1.09},
    "SAS": {"PG": 1.08, "SG": 1.09, "SF": 1.07, "PF": 1.05, "C": 0.95}, # Wemby protège le C, mais le reste...
    "ATL": {"PG": 1.13, "SG": 1.12, "SF": 1.08, "PF": 1.06, "C": 1.05},
    "IND": {"PG": 1.10, "SG": 1.11, "SF": 1.09, "PF": 1.12, "C": 1.08}, # Pace rapide + Défense faible
    "UTA": {"PG": 1.11, "SG": 1.10, "SF": 1.09, "PF": 1.12, "C": 1.08},
    "TOR": {"PG": 1.08, "SG": 1.09, "SF": 1.07, "PF": 1.10, "C": 1.06},
    "CHI": {"PG": 1.09, "SG": 1.10, "SF": 1.06, "PF": 1.05, "C": 1.08},
    "MEM": {"PG": 1.02, "SG": 1.01, "SF": 1.00, "PF": 0.95, "C": 1.02}, # JJJ tient le PF
}

# 🛡️ LISTE DES PILIERS DÉFENSIFS (Avec POSTE)
KEY_DEFENDERS_IMPACT = {
    "Rudy Gobert": {"pos": "C", "impact": 0.15},
    "Anthony Davis": {"pos": "C", "impact": 0.12},
    "Joel Embiid": {"pos": "C", "impact": 0.12},
    "Bam Adebayo": {"pos": "C", "impact": 0.10},
    "Victor Wembanyama": {"pos": "C", "impact": 0.12},
    "Jarrett Allen": {"pos": "C", "impact": 0.09},
    "Chet Holmgren": {"pos": "C", "impact": 0.10},
    "Giannis Antetokounmpo": {"pos": "F", "impact": 0.10},
    "Evan Mobley": {"pos": "F", "impact": 0.09},
    "Draymond Green": {"pos": "F", "impact": 0.10},
    "OG Anunoby": {"pos": "F", "impact": 0.08},
    "Jaren Jackson Jr.": {"pos": "F", "impact": 0.10},
    "Herbert Jones": {"pos": "F", "impact": 0.07},
    "Jrue Holiday": {"pos": "G", "impact": 0.08},
    "Derrick White": {"pos": "G", "impact": 0.07},
    "Alex Caruso": {"pos": "G", "impact": 0.07},
    "Lu Dort": {"pos": "G", "impact": 0.07},
}

def get_pace_factor(team_code):
    return PACE_RATINGS.get(team_code, 1.0)

def get_defensive_factor(opponent_code, player_position="G"):
    """
    Récupère le facteur défensif spécifique au poste du joueur.
    
    Args:
        opponent_code (str): Code de l'équipe adverse (ex: "MIN")
        player_position (str): Position du joueur (ex: "PG", "C", "G-F")
    """
    if opponent_code not in DVP_RATINGS:
        return 1.0
    
    team_dvp = DVP_RATINGS[opponent_code]
    
    # Normalisation de la position (G-F -> G, etc.)
    # On prend la position primaire
    pos = player_position.split('-')[0] if player_position else "G"
    
    # Mapping simple si la position n'est pas standard
    if pos not in ["PG", "SG", "SF", "PF", "C"]:
        if "G" in pos: pos = "SG"
        elif "F" in pos: pos = "SF"
        elif "C" in pos: pos = "C"
        else: pos = "SG" # Défaut
        
    return team_dvp.get(pos, 1.0)

def adjust_defense_for_injuries(opponent_code, opponent_roster):
    """Ajuste les facteurs selon les absents."""
    adjustments = {"points": 0.0, "rebounds": 0.0, "assists": 0.0}
    missing_defenders = []

    if not opponent_roster:
        return adjustments, []

    for player in opponent_roster:
        name = player.get("full_name")
        status = player.get("injury_status", "HEALTHY")
        
        if name in KEY_DEFENDERS_IMPACT and status == "OUT":
            data = KEY_DEFENDERS_IMPACT[name]
            impact = data["impact"]
            pos = data["pos"]
            
            missing_defenders.append(f"{name} ({pos})")
            
            if pos == "C":
                adjustments["rebounds"] += impact * 1.5
                adjustments["points"] += impact * 1.2
                adjustments["assists"] += impact * 0.5
            elif pos == "G":
                adjustments["assists"] += impact * 1.5
                adjustments["points"] += impact * 1.0
                adjustments["rebounds"] += impact * 0.2
            elif pos == "F":
                adjustments["points"] += impact * 1.0
                adjustments["rebounds"] += impact * 0.8
                adjustments["assists"] += impact * 0.8
            
    return adjustments, missing_defenders

def get_defense_analysis(opponent_code, missing_defenders=None, pace_factor=1.0, player_pos="G"):
    """Génère l'analyse textuelle DvP."""
    if opponent_code not in DVP_RATINGS:
        return {"rating": "Inconnue", "description": "N/A", "opportunity": False}

    # On récupère le rating spécifique au poste
    base_rating = get_defensive_factor(opponent_code, player_pos)
    
    rating_label = ""
    desc = ""
    opp = False

    if base_rating <= 0.92:
        rating_label = "Elite 🛡️"
        desc = f"{opponent_code} étouffe les {player_pos}."
    elif base_rating <= 0.98:
        rating_label = "Solide 🔒"
        desc = f"{opponent_code} défend bien sur ce poste."
    elif base_rating <= 1.05:
        rating_label = "Moyenne ⚖️"
        desc = f"Défense standard contre les {player_pos}."
    elif base_rating <= 1.10:
        rating_label = "Faible 📉"
        desc = f"{opponent_code} a du mal contre les {player_pos}."
        opp = True
    else:
        rating_label = "Passoire 🚨"
        desc = f"Autoroute pour les {player_pos} face à {opponent_code} !"
        opp = True

    if pace_factor > 1.02: desc += " (Rythme rapide ⚡️)"
    elif pace_factor < 0.97: desc += " (Rythme lent 🐢)"

    if missing_defenders:
        names = ", ".join(missing_defenders)
        desc += f" ⚠️ {names} OUT ! Défense affaiblie."
        rating_label += " (Affaiblie)"
        opp = True

    return {
        "rating": rating_label,
        "description": desc,
        "opportunity": opp
    }

NBA_TEAM_CODES = {
    1610612737: "ATL", 1610612738: "BOS", 1610612739: "CLE", 1610612740: "NOP",
    1610612741: "CHI", 1610612742: "DAL", 1610612743: "DEN", 1610612744: "GSW",
    1610612745: "HOU", 1610612746: "LAC", 1610612747: "LAL", 1610612748: "MIA",
    1610612749: "MIL", 1610612750: "MIN", 1610612751: "BKN", 1610612752: "NYK",
    1610612753: "ORL", 1610612754: "IND", 1610612755: "PHI", 1610612756: "PHX",
    1610612757: "POR", 1610612758: "SAC", 1610612759: "SAS", 1610612760: "OKC",
    1610612761: "TOR", 1610612762: "UTA", 1610612763: "MEM", 1610612764: "WAS",
    1610612765: "DET", 1610612766: "CHA",
}
