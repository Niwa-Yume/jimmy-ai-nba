"""
Module de calcul de probabilités pour les paliers (Milestones).

Utilise la Loi Normale (Gaussienne) pour estimer la probabilité qu'un joueur atteigne un certain score.
La Loi de Poisson est souvent citée, mais pour le basket (scores élevés > 10), la Loi Normale est plus adaptée et précise.
"""

import math

def cumulative_distribution_function(x, mean, std_dev):
    """
    Fonction de répartition de la loi normale (CDF).
    Calcule la probabilité qu'une variable soit INFÉRIEURE ou ÉGALE à x.
    """
    # Protection contre std_dev nul (loi dégénérée en mean)
    try:
        # Protection multiple : None, NaN, zéro
        if std_dev is None:
            return 0.0 if x < mean else 1.0
        # NaN handling
        try:
            if math.isnan(std_dev):
                return 0.0 if x < mean else 1.0
        except Exception:
            pass
        # Close to zero
        if std_dev == 0 or math.isclose(float(std_dev), 0.0):
            return 0.0 if x < mean else 1.0
        z = (x - mean) / (float(std_dev) * math.sqrt(2))
        return 0.5 * (1 + math.erf(z))
    except ZeroDivisionError:
        return 0.0 if x < mean else 1.0
    except Exception:
        return 0.0

def calculate_milestone_probabilities(projection, std_dev, stat_type="points"):
    """
    Calcule les probabilités d'atteindre différents paliers.
    
    Args:
        projection (float): La projection ajustée de Jimmy (ex: 24.5)
        std_dev (float): L'écart-type (volatilité) du joueur (ex: 5.2)
        stat_type (str): Le type de stat pour définir les paliers pertinents.
        
    Returns:
        list[dict]: Liste de paliers avec leur probabilité.
    """
    
    # Si l'écart-type est nul ou inconnu, on prend une valeur par défaut (environ 20-25% de la moyenne)
    if not std_dev or std_dev == 0:
        std_dev = projection * 0.25

    # Définition des paliers selon le type de stat
    if stat_type == "points":
        # Paliers : 10, 15, 20, 25, 30, 35, 40...
        # On commence un peu en dessous de la projection
        start = max(10, int(projection) - 10)
        start = start - (start % 5) # Arrondir au multiple de 5 inférieur
        milestones = [x for x in range(start, int(projection) + 15, 5)]
        
    elif stat_type in ["rebounds", "assists"]:
        # Paliers : 4, 6, 8, 10, 12...
        start = max(2, int(projection) - 4)
        start = start - (start % 2)
        milestones = [x for x in range(start, int(projection) + 8, 2)]
        
    elif stat_type == "three_points_made":
        # Paliers : 1, 2, 3, 4, 5...
        milestones = [1, 2, 3, 4, 5, 6]
        
    else: # Steals, Blocks
        milestones = [1, 2, 3]

    results = []
    
    for m in milestones:
        if m <= 0: continue
        
        # On veut P(X >= m).
        # Dans une loi continue, P(X >= m) = 1 - P(X < m)
        # Pour être précis avec des entiers discrets (basket), on prend m - 0.5 comme seuil
        # Ex: Pour avoir "au moins 20", il faut être > 19.5
        prob = 1 - cumulative_distribution_function(m - 0.5, projection, std_dev)
        
        # Convertir en pourcentage arrondi
        prob_percent = round(prob * 100, 1)
        
        # On ne garde que les probas pertinentes (entre 5% et 99%)
        if 5 <= prob_percent <= 99.9:
            label = ""
            if prob_percent >= 90: label = "🔒 Safe"
            elif prob_percent >= 70: label = "✅ Probable"
            elif prob_percent >= 50: label = "⚖️ 50/50"
            elif prob_percent >= 30: label = "⚠️ Risqué"
            else: label = "🔥 Jackpot"
            
            results.append({
                "milestone": f"{m}+",
                "value": m,
                "probability": prob_percent,
                "label": label
            })
            
    # Trier par valeur de palier croissant
    results.sort(key=lambda x: x["value"])
    
    return results
