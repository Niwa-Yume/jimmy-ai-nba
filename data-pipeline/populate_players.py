import psycopg2
from nba_api.stats.static import players

# --- CONFIGURATION ---
DB_PARAMS = {
    "dbname": "jimmy_nba_db",
    "user": "jimmy_user",
    "password": "secure_password_123",
    "host": "localhost",
    "port": "5432"
}


def sync_players():
    # 1. EXTRACT: Récupérer les données depuis la NBA
    print("🏀 Récupération des joueurs actifs depuis l'API NBA...")
    nba_players = players.get_active_players()
    print(f"✅ {len(nba_players)} joueurs trouvés (Ex: {nba_players[0]['full_name']})")

    try:
        # 2. LOAD: Connexion à la BDD
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        print("🔄 Insertion en base de données...")

        # On prépare le compteur pour le feedback
        count = 0

        for p in nba_players:
            # Requête SQL sécurisée
            # ON CONFLICT DO NOTHING évite de planter si le joueur existe déjà
            sql = """
                  INSERT INTO player (nba_player_id, full_name, is_active, position)
                  VALUES (%s, %s, %s, %s) ON CONFLICT (nba_player_id) DO \
                  UPDATE \
                      SET is_active = EXCLUDED.is_active; \
                  """
            # L'API ne donne pas toujours la position ici, on met 'Unknown' par défaut pour l'instant
            cur.execute(sql, (p['id'], p['full_name'], True, 'Unknown'))
            count += 1

        conn.commit()
        print(f"🎉 Succès ! {count} joueurs ont été traités/mis à jour dans la table 'player'.")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Erreur : {e}")


if __name__ == "__main__":
    sync_players()