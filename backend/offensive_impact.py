"""
Module de gestion de l'impact offensif (Usage Rate).

🚀 Boost d'Opportunité
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Ce module calcule l'augmentation des stats d'un joueur quand une STAR de son équipe est absente.
C'est le principe du "Usage Rate" : quand le patron n'est pas là, les lieutenants prennent plus de tirs.
"""

# 🌟 LISTE DES STARS OFFENSIVES (Les "Alphas")
# Si un de ces joueurs est OUT, ses coéquipiers reçoivent un boost.
TEAM_STARS = {
    "ATL": ["Trae Young"],
    "BOS": ["Jayson Tatum", "Jaylen Brown"],
    "BKN": ["Cam Thomas"],
    "CHA": ["LaMelo Ball"],
    "CHI": ["Zach LaVine"],
    "CLE": ["Donovan Mitchell", "Darius Garland"],
    "DAL": ["Luka Doncic", "Kyrie Irving"],
    "DEN": ["Nikola Jokic", "Jamal Murray"],
    "DET": ["Cade Cunningham"],
    "GSW": ["Stephen Curry"],
    "HOU": ["Alperen Sengun", "Jalen Green"],
    "IND": ["Tyrese Haliburton", "Pascal Siakam"],
    "LAC": ["Kawhi Leonard", "James Harden"],
    "LAL": ["LeBron James", "Anthony Davis"],
    "MEM": ["Ja Morant", "Desmond Bane"],
    "MIA": ["Jimmy Butler", "Tyler Herro"],
    "MIL": ["Giannis Antetokounmpo", "Damian Lillard"],
    "MIN": ["Anthony Edwards", "Karl-Anthony Towns"], # KAT est parti mais pour l'exemple historique
    "NOP": ["Zion Williamson", "Brandon Ingram"],
    "NYK": ["Jalen Brunson", "Karl-Anthony Towns"],
    "OKC": ["Shai Gilgeous-Alexander"],
    "ORL": ["Paolo Banchero", "Franz Wagner"],
    "PHI": ["Joel Embiid", "Tyrese Maxey", "Paul George"],
    "PHX": ["Kevin Durant", "Devin Booker"],
    "POR": ["Anfernee Simons"],
    "SAC": ["De'Aaron Fox", "Domantas Sabonis"],
    "SAS": ["Victor Wembanyama"],
    "TOR": ["Scottie Barnes"],
    "UTA": ["Lauri Markkanen"],
    "WAS": ["Kyle Kuzma", "Jordan Poole"]
}

def get_offensive_boost(player_name, team_code, team_roster):
    """
    Calcule le boost offensif si une star est absente.
    
    Args:
        player_name (str): Le joueur qu'on analyse (ex: "Kyrie Irving")
        team_code (str): Son équipe (ex: "DAL")
        team_roster (list): Le roster de son équipe avec statuts de blessure
        
    Returns:
        dict: Multiplicateurs {"points": 1.15, "assists": 1.20, ...}
        list: Liste des stars absentes (pour l'explication)
    """
    # Facteurs neutres par défaut
    boosts = {"points": 1.0, "rebounds": 1.0, "assists": 1.0}
    missing_stars = []

    if not team_code or team_code not in TEAM_STARS or not team_roster:
        return boosts, missing_stars

    stars_list = TEAM_STARS[team_code]

    for teammate in team_roster:
        t_name = teammate.get("full_name")
        t_status = teammate.get("injury_status", "HEALTHY")

        # Si le coéquipier est une Star, qu'il est OUT, et que ce n'est pas MOI
        if t_name in stars_list and t_status == "OUT" and t_name != player_name:
            missing_stars.append(t_name)
            
            # 🚀 APPLICATION DU BOOST (CUMULATIF)
            # Un lieutenant prend environ 15-20% de volume en plus sans la star
            boosts["points"] += 0.15    # +15% de points
            boosts["assists"] += 0.15   # +15% de passes (ballon plus souvent en main)
            boosts["rebounds"] += 0.05  # +5% rebonds (impact mineur)

    return boosts, missing_stars
