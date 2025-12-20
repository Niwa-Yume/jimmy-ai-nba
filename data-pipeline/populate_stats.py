import psycopg2
from nba_api.stats.endpoints import playergamelog
import time

# --- CONFIGURATION ---
DB_PARAMS = {
    "dbname": "jimmy_nba_db",
    "user": "jimmy_user",
    "password": "secure_password_123",
    "host": "localhost",
    "port": "5432"
}

# ID de Luka Dončić (trouvé via ton script précédent ou recherche)
LUKA_ID = 1629029


def sync_luka_stats():
    print(f"🏀 Récupération des stats de Luka Dončić ({LUKA_ID})...")

    # 1. Appel API : On demande le 'GameLog' (Journal des matchs) de la saison 2023-24
    # Source 76: "Game logs clairs"
    log = playergamelog.PlayerGameLog(player_id=LUKA_ID, season='2023-24')
    games = log.get_normalized_dict()['PlayerGameLog']

    # On prend juste les 5 derniers pour le test
    last_5_games = games[:5]
    print(f"✅ {len(last_5_games)} matchs récupérés.")

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        for g in last_5_games:
            game_nba_id = g['Game_ID']
            game_date = g['GAME_DATE']  # Format "OCT 25, 2023"

            # --- ÉTAPE A : Créer le Match dans la table 'game' ---
            # On doit d'abord s'assurer que le match existe avant de lier des stats
            # Pour simplifier ce MVP, on met des valeurs NULL pour les équipes/scores
            cur.execute("""
                        INSERT INTO game (nba_game_id, game_date, status)
                        VALUES (%s, %s, 'FINISHED') ON CONFLICT (nba_game_id) DO NOTHING;
                        """, (game_nba_id, game_date))

            # Récupérer l'ID interne de notre joueur (Luka)
            cur.execute("SELECT id FROM player WHERE nba_player_id = %s", (LUKA_ID,))
            player_internal_id = cur.fetchone()[0]

            # Récupérer l'ID interne du match qu'on vient d'insérer/trouver
            cur.execute("SELECT id FROM game WHERE nba_game_id = %s", (game_nba_id,))
            game_internal_id = cur.fetchone()[0]

            # --- ÉTAPE B : Insérer les Stats (Le cœur du projet) ---
            # Source 14: "Luka 15+ points..." -> On stocke les points, rebonds, passes
            print(f"   -> Insertion stats match {game_nba_id}: {g['PTS']} pts, {g['REB']} reb, {g['AST']} pass")

            cur.execute("""
                        INSERT INTO player_game_stats
                        (player_id, game_id, points, rebounds, assists, minutes_played, fg_percentage)
                        VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (player_id, game_id) DO NOTHING;
                        """, (
                            player_internal_id,
                            game_internal_id,
                            g['PTS'],
                            g['REB'],
                            g['AST'],
                            g['MIN'],  # Minutes
                            g['FG_PCT']  # Pourcentage au tir
                        ))

        conn.commit()
        print("🎉 Stats de Luka sauvegardées en BDD !")
        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Erreur : {e}")


if __name__ == "__main__":
    sync_luka_stats()