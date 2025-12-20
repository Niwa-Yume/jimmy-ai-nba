from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
import pandas as pd
from database import get_db, engine
import models

# Initialisation de l'app
app = FastAPI(title="Jimmy.AI API", description="Moteur de prédiction NBA")

# --- ROUTES ---

@app.get("/")
def read_root():
    return {"message": "Jimmy.AI Backend is running! 🏀"}

@app.get("/players/")
def get_all_players(db: Session = Depends(get_db)):
    """Récupère la liste de tous les joueurs en base."""
    return db.query(models.Player).limit(100).all()

@app.get("/projection/{player_id}")
def compute_projection(player_id: int, db: Session = Depends(get_db)):
    # 1. Récupération
    player = db.query(models.Player).filter(models.Player.id == player_id).first()
    if not player:
        raise HTTPException(status_code=404, detail="Joueur non trouvé")

    query = f"SELECT * FROM player_game_stats WHERE player_id = {player_id} ORDER BY game_id DESC"  # On trie par date
    df = pd.read_sql(query, engine)

    if df.empty:
        return {"message": "Pas assez de données"}

    # 2. La Logique "Jimmy Highroller" (V2)
    # On simule une moyenne de saison (car on n'a pas encore tout scrapé)
    # Dans le futur, cette info viendra de la table 'player'
    simulated_season_avg = 28.5

    # Calcul de la moyenne sur les matchs stockés (Forme Récente)
    recent_avg = df['points'].mean()

    # Formule Pondérée (Source doc: 104)
    # On donne plus de poids à la forme du moment (les stats qu'on a en base)
    weighted_projection = (recent_avg * 0.7) + (simulated_season_avg * 0.3)

    # 3. Analyse du Risque (Source doc: 120, 131)
    # L'écart type (std) mesure si le joueur est régulier ou instable
    consistency = df['points'].std()

    risk_level = "FAIBLE"
    if consistency > 5.0:  # Si ses points varient de plus de 5 d'un match à l'autre
        risk_level = "ÉLEVÉ (Joueur instable)"

    # 4. Le Prompt pour l'IA (Préparation Sprint 4)
    # C'est ce texte qu'on enverra à ChatGPT plus tard pour générer la phrase "style Jimmy"
    system_prompt_data = f"""
    Analyse pour {player.full_name}:
    - Moyenne récente: {recent_avg:.1f} pts
    - Régularité (écart-type): {consistency:.1f}
    - Projection Algorithmique: {weighted_projection:.1f} pts
    - Risque: {risk_level}
    """

    return {
        "player": player.full_name,
        "math_projection": round(weighted_projection, 1),
        "risk_analysis": risk_level,
        "consistency_score": round(consistency, 2),
        "data_for_llm": system_prompt_data
    }