import psycopg2
from nba_api.stats.endpoints import playergamelog
import hashlib

# --- CONFIGURATION ---
DB_PARAMS = {
    "dbname": "jimmy_nba_db",
    "user": "jimmy_user",
    "password": "secure_password_123",
    "host": "localhost",
    "port": "5432"
}

def sync_player_stats(nba_player_id, season='2024-25', limit=82):
    """
    Récupère et sauvegarde les stats d'un joueur (Points, Rebonds, Passes, 3PM, Steals, Blocks, Matchup).
    """
    print(f"🏀 Récupération des stats du joueur {nba_player_id}...")

    # 1. Appel API
    log = playergamelog.PlayerGameLog(player_id=nba_player_id, season=season)
    games = log.get_normalized_dict()['PlayerGameLog']

    # Par défaut on récupère jusqu'à 'limit' matchs (82 si non précisé)
    if limit:
        games = games[:limit]

    print(f"✅ {len(games)} matchs récupérés.")

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        # Vérifier que le joueur existe en BDD
        cur.execute("SELECT id FROM player WHERE nba_player_id = %s", (nba_player_id,))
        player_row = cur.fetchone()

        if not player_row:
            print(f"❌ Joueur {nba_player_id} introuvable en BDD.")
            cur.close()
            conn.close()
            return (0, 0)

        player_internal_id = player_row[0]
        new_games = 0
        cached_games = 0
        updated_count = 0

        for g in games:
            game_nba_id = g['Game_ID']
            game_date = g['GAME_DATE']

            # --- ÉTAPE A : Créer le Match (si inexistant) ---
            cur.execute("""
                        INSERT INTO game (nba_game_id, game_date, status)
                        VALUES (%s, %s, 'FINISHED') ON CONFLICT (nba_game_id) DO NOTHING;
                        """, (game_nba_id, game_date))

            cur.execute("SELECT id FROM game WHERE nba_game_id = %s", (game_nba_id,))
            game_internal_id = cur.fetchone()[0]

            # Calculer un content_hash unique des stats importantes pour l'idempotence
            stats_repr = f"{g['PTS']}-{g['REB']}-{g['AST']}-{g.get('STL',0)}-{g.get('BLK',0)}-{g.get('FG3M',0)}-{g.get('MIN','')}-{g.get('FG_PCT','')}"
            content_hash = hashlib.sha256(stats_repr.encode('utf-8')).hexdigest()

            # Vérifier si les stats existent déjà et récupérer le hash
            cur.execute("""
                SELECT id, content_hash FROM player_game_stats 
                WHERE player_id = %s AND game_id = %s
            """, (player_internal_id, game_internal_id))

            row = cur.fetchone()

            if not row:
                print(f"   -> Insertion stats match {game_nba_id}: {g['PTS']} pts, {g['MATCHUP']}")

                # INSERT with content_hash and timestamps
                cur.execute("""
                            INSERT INTO player_game_stats
                            (player_id, game_id, points, rebounds, assists, steals, blocks, three_points_made, matchup, minutes_played, fg_percentage, content_hash, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                            ON CONFLICT (player_id, game_id) DO NOTHING;
                            """, (
                                player_internal_id,
                                game_internal_id,
                                g['PTS'],
                                g['REB'],
                                g['AST'],
                                g.get('STL', 0),
                                g.get('BLK', 0),
                                g.get('FG3M', 0),
                                g.get('MATCHUP'), # ✅ Nouveau champ
                                g.get('MIN'),
                                g.get('FG_PCT'),
                                content_hash
                            ))
                new_games += 1
            else:
                existing_id, existing_hash = row[0], row[1]
                if not existing_hash:
                    existing_hash = ''

                # Si le hash a changé, on met à jour la ligne (stats modifiées ou amélioration des données)
                if existing_hash != content_hash:
                    cur.execute("""
                        UPDATE player_game_stats
                        SET points = %s, rebounds = %s, assists = %s, steals = %s, blocks = %s, three_points_made = %s,
                            matchup = %s, minutes_played = %s, fg_percentage = %s, content_hash = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (
                        g['PTS'], g['REB'], g['AST'], g.get('STL', 0), g.get('BLK', 0), g.get('FG3M', 0),
                        g.get('MATCHUP'), g.get('MIN'), g.get('FG_PCT'), content_hash, existing_id
                    ))
                    updated_count += 1
                    print(f"   🔄 Mise à jour stats match {game_nba_id} (id:{existing_id})")
                else:
                    # Optionnel : Mettre à jour le matchup si manquant
                    cur.execute("""
                        UPDATE player_game_stats 
                        SET matchup = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s AND (matchup IS NULL OR matchup = '')
                    """, (g.get('MATCHUP'), existing_id))
                    cached_games += 1

        conn.commit()
        print(f"🎉 Stats du joueur {nba_player_id} sauvegardées !")
        print(f"   📊 {new_games} nouveaux, {cached_games} en cache, {updated_count} mises à jour")
        cur.close()
        conn.close()

        return (new_games, cached_games, updated_count)

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return (0, 0, 0)

if __name__ == "__main__":
    # Test avec Luka
    sync_player_stats(1629029, limit=5)
