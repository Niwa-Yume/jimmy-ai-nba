import psycopg2
from datetime import datetime
import os

# Configuration BDD
DB_PARAMS = {
    "dbname": "jimmy_nba_db",
    "user": "jimmy_user",
    "password": "secure_password_123",
    "host": "localhost",
    "port": "5432"
}

def check_health():
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        print("🏥 --- DIAGNOSTIC DE LA DONNÉE --- 🏥\n")

        # 1. Vérifier les Matchs
        cur.execute("SELECT COUNT(*), MAX(last_fetched_at) FROM games_schedule")
        games_count, last_games_fetch = cur.fetchone()
        print(f"🏀 MATCHS :")
        print(f"   - Total en base : {games_count}")
        print(f"   - Dernière synchro : {last_games_fetch} (Il y a {(datetime.now() - last_games_fetch).seconds // 60} min)" if last_games_fetch else "   - Jamais synchronisé")

        # 2. Vérifier les Blessures
        cur.execute("SELECT COUNT(*), MAX(last_verified_at) FROM player_injuries WHERE is_active = TRUE")
        injuries_count, last_injury_fetch = cur.fetchone()
        print(f"\n🚑 BLESSURES (Actives) :")
        print(f"   - Total actives : {injuries_count}")
        print(f"   - Dernière synchro : {last_injury_fetch} (Il y a {(datetime.now() - last_injury_fetch).seconds // 60} min)" if last_injury_fetch else "   - Jamais synchronisé")

        # 3. Vérifier les Joueurs
        cur.execute("SELECT COUNT(*) FROM player")
        players_count = cur.fetchone()[0]
        print(f"\n👤 JOUEURS :")
        print(f"   - Total référencés : {players_count}")

        # 4. Vérifier les Stats
        cur.execute("SELECT COUNT(*), MAX(updated_at) FROM player_game_stats")
        stats_count, last_stats_update = cur.fetchone()
        print(f"\n📊 STATS HISTORIQUES :")
        print(f"   - Lignes de stats : {stats_count}")
        print(f"   - Dernier ajout : {last_stats_update}")

        print("\n-------------------------------------")
        
        # Alerte si données vieilles
        if last_injury_fetch and (datetime.now() - last_injury_fetch).seconds > 7200: # 2 heures
            print("⚠️ ATTENTION : Les blessures datent de plus de 2h. Lancez 'python data-pipeline/sync_injuries_v2.py'")
        else:
            print("✅ Les blessures semblent à jour.")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Erreur de connexion BDD : {e}")

if __name__ == "__main__":
    check_health()
