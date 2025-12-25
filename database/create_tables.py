"""Script simple de création des tables games_schedule et player_injuries"""

import psycopg2

def create_tables():
    try:
        conn = psycopg2.connect(
            dbname='jimmy_nba_db',
            user='jimmy_user',
            password='secure_password_123',
            host='localhost'
        )
        cur = conn.cursor()

        print("🔧 Création de la table games_schedule...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS games_schedule (
                id SERIAL PRIMARY KEY,
                nba_game_id VARCHAR(50) UNIQUE NOT NULL,
                game_date DATE NOT NULL,
                game_time VARCHAR(20),
                home_team_code VARCHAR(3) NOT NULL,
                away_team_code VARCHAR(3) NOT NULL,
                home_team_id INTEGER,
                away_team_id INTEGER,
                status VARCHAR(20) DEFAULT 'SCHEDULED',
                home_score INTEGER,
                away_score INTEGER,
                arena VARCHAR(200),
                tv_broadcast VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ games_schedule créée")

        print("🔧 Création de la table player_injuries...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS player_injuries (
                id SERIAL PRIMARY KEY,
                player_id INTEGER REFERENCES player(id) ON DELETE CASCADE,
                nba_player_id INTEGER NOT NULL,
                status VARCHAR(50) NOT NULL,
                injury_type VARCHAR(100),
                injury_detail TEXT,
                injury_date DATE,
                expected_return DATE,
                play_probability INTEGER,
                source VARCHAR(50) DEFAULT 'ESPN',
                source_url TEXT,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("✅ player_injuries créée")

        print("🔧 Ajout colonnes à player...")
        try:
            cur.execute("ALTER TABLE player ADD COLUMN IF NOT EXISTS current_injury_status VARCHAR(50) DEFAULT 'HEALTHY'")
            cur.execute("ALTER TABLE player ADD COLUMN IF NOT EXISTS injury_updated_at TIMESTAMP")
            print("✅ Colonnes ajoutées")
        except Exception as e:
            print(f"⚠️ Colonnes déjà existantes ou erreur : {e}")

        # --- Ajouter colonnes pour l'idempotence des stats si manquantes ---
        try:
            print("🔧 Vérification des colonnes player_game_stats (content_hash/updated_at)...")
            cur.execute("ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS content_hash VARCHAR(128)")
            cur.execute("ALTER TABLE player_game_stats ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            print("✅ Colonnes player_game_stats mises à jour")
        except Exception as e:
            print(f"⚠️ Erreur ajout colonnes player_game_stats: {e}")

        conn.commit()

        # Vérifier
        cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'games_schedule'")
        if cur.fetchone()[0] > 0:
            print("\n🎉 SUCCESS ! Tables créées avec succès")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Erreur : {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    create_tables()
