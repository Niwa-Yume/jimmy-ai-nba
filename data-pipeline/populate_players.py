import psycopg2
import re
import os
from nba_api.stats.static import players, teams
import json
from datetime import datetime

# --- CONFIGURATION (compatibilité Docker + local) ---
DB_PARAMS = {
    "dbname": os.getenv("DB_NAME", "jimmy_nba_db"),
    "user": os.getenv("DB_USER", "jimmy_user"),
    "password": os.getenv("DB_PASSWORD", "secure_password_123"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}


def normalize_name(name: str) -> str:
    # Minimal normalization: lower, remove non-alphanum
    return re.sub(r"[^a-z0-9]", "", name.lower()) if name else ""


def start_ingestion_run(cur, source: str, scope: str = None, version_tag: str = None):
    cur.execute(
        """
        INSERT INTO ingestion_runs (source, scope, version_tag, status, started_at)
        VALUES (%s, %s, %s, 'running', %s)
        RETURNING id
        """,
        (source, scope, version_tag, datetime.utcnow())
    )
    return cur.fetchone()[0]


def finish_ingestion_run(cur, run_id: int, status: str = 'success', meta: dict | None = None):
    cur.execute(
        """
        UPDATE ingestion_runs
        SET status = %s,
            ended_at = %s,
            meta = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (status, datetime.utcnow(), json.dumps(meta or {}), datetime.utcnow(), run_id)
    )


def sync_players():
    # 1. EXTRACT: Récupérer les données depuis la NBA
    print("🏀 Récupération des joueurs actifs depuis l'API NBA...")
    nba_players = players.get_active_players()
    nba_teams = teams.get_teams()
    print(f"✅ {len(nba_players)} joueurs trouvés (Ex: {nba_players[0]['full_name']})")

    ingestion_run_id = None

    try:
        # 2. LOAD: Connexion à la BDD
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        ingestion_run_id = start_ingestion_run(cur, source="nba_api", scope="players+teams")

        print("🔄 Insertion en base de données (players + mappings + aliases)...")

        # Upsert teams (basic)
        for t in nba_teams:
            cur.execute(
                """
                INSERT INTO team (nba_team_id, code, name, conference, division, is_active)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (nba_team_id) DO UPDATE
                  SET code = EXCLUDED.code,
                      name = EXCLUDED.name,
                      conference = EXCLUDED.conference,
                      division = EXCLUDED.division,
                      is_active = EXCLUDED.is_active
                """,
                (
                    t.get('id'),
                    t.get('abbreviation'),
                    t.get('full_name'),
                    t.get('conference'),
                    t.get('division'),
                    True,
                ),
            )

        # Upsert players + mapping + alias
        for p in nba_players:
            cur.execute(
                """
                INSERT INTO player (nba_player_id, full_name, is_active, position)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (nba_player_id) DO UPDATE
                  SET is_active = EXCLUDED.is_active,
                      full_name = EXCLUDED.full_name
                RETURNING id
                """,
                (p['id'], p['full_name'], True, 'Unknown'),
            )
            player_id = cur.fetchone()[0]

            # id_mappings
            cur.execute(
                """
                INSERT INTO id_mappings (entity_type, entity_id, source, external_id, display_name)
                VALUES ('player', %s, 'nba', %s, %s)
                ON CONFLICT (entity_type, source, external_id) DO UPDATE
                  SET display_name = EXCLUDED.display_name,
                      entity_id = EXCLUDED.entity_id
                """,
                (player_id, p['id'], p['full_name']),
            )

            # aliases
            norm = normalize_name(p['full_name'])
            cur.execute(
                """
                INSERT INTO aliases (entity_type, entity_id, source, alias, normalized_alias)
                VALUES ('player', %s, 'nba', %s, %s)
                ON CONFLICT (entity_type, alias, source) DO UPDATE
                  SET normalized_alias = EXCLUDED.normalized_alias
                """,
                (player_id, p['full_name'], norm),
            )

        finish_ingestion_run(cur, ingestion_run_id, status='success', meta={
            "players": len(nba_players),
            "teams": len(nba_teams),
        })

        conn.commit()
        print(f"🎉 Succès ! {len(nba_players)} joueurs et {len(nba_teams)} équipes synchronisés.")

        cur.close()
        conn.close()

    except Exception as e:
        if ingestion_run_id:
            try:
                finish_ingestion_run(cur, ingestion_run_id, status='failed', meta={"error": str(e)})
                conn.commit()
            except Exception:
                pass
        print(f"❌ Erreur : {e}")


if __name__ == "__main__":
    sync_players()