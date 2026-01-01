"""
Module de synchronisation des matchs NBA de la semaine (Version HTTP directe).

Utilise l'API officielle NBA.com via requêtes HTTP simples.
"""

import psycopg2
import requests
from datetime import datetime, timedelta
import json

# Configuration BDD
DB_PARAMS = {
    "dbname": "jimmy_nba_db",
    "user": "jimmy_user",
    "password": "secure_password_123",
    "host": "localhost",
    "port": "5432"
}


def fetch_weekly_games_http():
    """
    Récupère les matchs via l'API NBA.com (méthode HTTP directe).
    """
    print("🏀 Récupération des matchs via NBA.com...")

    games = []
    today = datetime.now()

    # Récupérer les matchs pour les 7 prochains jours
    for day_offset in range(8):  # 0 à 7 jours
        target_date = today + timedelta(days=day_offset)
        date_str = target_date.strftime('%Y-%m-%d')

        try:
            # API officielle NBA.com (format v2)
            url = f"https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"

            # Pour des dates spécifiques, utiliser l'endpoint schedule
            schedule_url = "https://cdn.nba.com/static/json/staticData/scheduleLeagueV2_1.json"

            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://www.nba.com/'
            }

            response = requests.get(schedule_url, headers=headers, timeout=10)

            if response.ok:
                data = response.json()

                # Parser le schedule
                game_dates = data.get('leagueSchedule', {}).get('gameDates', [])

                for game_date_entry in game_dates:
                    game_date_str = game_date_entry.get('gameDate', '')

                    # Filtrer les 7 prochains jours
                    try:
                        game_date = datetime.strptime(game_date_str, '%m/%d/%Y %H:%M:%S').date()
                    except:
                        continue

                    if game_date < today.date() or game_date > (today + timedelta(days=7)).date():
                        continue

                    for game in game_date_entry.get('games', []):
                        games.append({
                            'nba_game_id': game.get('gameId'),
                            'game_date': game_date,
                            'game_time': game.get('gameDateTimeUTC', ''),
                            'home_team_code': game.get('homeTeam', {}).get('teamTricode'),
                            'away_team_code': game.get('awayTeam', {}).get('teamTricode'),
                            'home_team_id': game.get('homeTeam', {}).get('teamId'),
                            'away_team_id': game.get('awayTeam', {}).get('teamId'),
                            'status': 'SCHEDULED',
                            'arena': game.get('arenaName'),
                        })

                break  # Si succès, sortir de la boucle

        except Exception as e:
            print(f"   ⚠️ Erreur pour {date_str}: {e}")
            continue

    # Fallback : utiliser l'endpoint simple "today"
    if not games:
        print("   Tentative avec l'endpoint 'today'...")
        try:
            url = "https://cdn.nba.com/static/json/liveData/scoreboard/todaysScoreboard_00.json"
            response = requests.get(url, headers=headers, timeout=10)

            if response.ok:
                data = response.json()
                scoreboard = data.get('scoreboard', {})

                for game in scoreboard.get('games', []):
                    game_date_str = game.get('gameTimeUTC', '')[:10]

                    try:
                        game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()
                    except:
                        game_date = today.date()

                    games.append({
                        'nba_game_id': game.get('gameId'),
                        'game_date': game_date,
                        'game_time': game.get('gameTimeUTC', '')[-8:] if game.get('gameTimeUTC') else None,
                        'home_team_code': game.get('homeTeam', {}).get('teamTricode'),
                        'away_team_code': game.get('awayTeam', {}).get('teamTricode'),
                        'home_team_id': game.get('homeTeam', {}).get('teamId'),
                        'away_team_id': game.get('awayTeam', {}).get('teamId'),
                        'status': 'SCHEDULED',
                        'home_score': game.get('homeTeam', {}).get('score'),
                        'away_score': game.get('awayTeam', {}).get('score'),
                        'arena': None
                    })

        except Exception as e:
            print(f"   ❌ Erreur fallback : {e}")

    print(f"✅ {len(games)} matchs trouvés")
    return games


def start_ingestion_run(cur, source: str, scope: str = None, version_tag: str = None):
    cur.execute(
        """
        INSERT INTO ingestion_runs (source, scope, version_tag, status, started_at)
        VALUES (%s, %s, %s, 'running', CURRENT_TIMESTAMP)
        RETURNING id
        """,
        (source, scope, version_tag)
    )
    return cur.fetchone()[0]


def finish_ingestion_run(cur, run_id: int, status: str = 'success', meta: dict | None = None):
    cur.execute(
        """
        UPDATE ingestion_runs
        SET status = %s,
            ended_at = CURRENT_TIMESTAMP,
            meta = %s,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = %s
        """,
        (status, json.dumps(meta or {}), run_id)
    )


def sync_weekly_games(force_refresh=False):
    """Synchronise les matchs de la semaine en BDD."""
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        ingestion_run_id = start_ingestion_run(cur, source="nba.com", scope="games_schedule")

        # Vérifier le cache
        if not force_refresh:
            cur.execute("""
                SELECT MAX(last_fetched_at) 
                FROM games_schedule 
                WHERE game_date >= CURRENT_DATE
            """)
            last_fetch = cur.fetchone()[0]

            if last_fetch:
                time_since = datetime.now() - last_fetch
                if time_since < timedelta(hours=6):
                    cur.execute("""
                        SELECT COUNT(*) FROM games_schedule 
                        WHERE game_date >= CURRENT_DATE 
                        AND game_date <= CURRENT_DATE + INTERVAL '7 days'
                    """)
                    cached = cur.fetchone()[0]
                    print(f"📦 Cache valide : {cached} matchs")
                    finish_ingestion_run(cur, ingestion_run_id, status='cached', meta={"cached": cached})
                    conn.commit()
                    cur.close()
                    conn.close()
                    return {"new": 0, "updated": 0, "cached": cached}

        # Fetch games
        games = fetch_weekly_games_http()

        if not games:
            finish_ingestion_run(cur, ingestion_run_id, status='failed', meta={"reason": "no_games"})
            conn.commit()
            cur.close()
            conn.close()
            return {"new": 0, "updated": 0, "cached": 0}

        new_count = 0
        updated_count = 0

        for game in games:
            if not game.get('nba_game_id'):
                continue

            # Check si existe
            cur.execute("""
                SELECT id FROM games_schedule WHERE nba_game_id = %s
            """, (game['nba_game_id'],))

            if cur.fetchone():
                # Update
                cur.execute("""
                    UPDATE games_schedule 
                    SET status = %s,
                        home_score = %s,
                        away_score = %s,
                        last_fetched_at = CURRENT_TIMESTAMP
                    WHERE nba_game_id = %s
                """, (game.get('status', 'SCHEDULED'), game.get('home_score'),
                      game.get('away_score'), game['nba_game_id']))
                updated_count += 1
            else:
                # Insert
                cur.execute("""
                    INSERT INTO games_schedule 
                    (nba_game_id, game_date, game_time, home_team_code, away_team_code,
                     home_team_id, away_team_id, status, home_score, away_score, arena)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    game['nba_game_id'], game['game_date'], game.get('game_time'),
                    game['home_team_code'], game['away_team_code'],
                    game.get('home_team_id'), game.get('away_team_id'),
                    game.get('status', 'SCHEDULED'), game.get('home_score'),
                    game.get('away_score'), game.get('arena')
                ))
                new_count += 1

        finish_ingestion_run(cur, ingestion_run_id, status='success', meta={
            "new": new_count,
            "updated": updated_count,
            "total": len(games)
        })

        conn.commit()
        print(f"🎉 Matchs synchronisés ! New: {new_count}, Updated: {updated_count}")
        cur.close()
        conn.close()

        return {"new": new_count, "updated": updated_count, "cached": 0}

    except Exception as e:
        try:
            finish_ingestion_run(cur, ingestion_run_id, status='failed', meta={"error": str(e)})
            conn.commit()
        except Exception:
            pass
        print(f"❌ Erreur sync_weekly_games: {e}")
        return {"new": 0, "updated": 0, "cached": 0}


def get_weekly_games_from_db():
    """Récupère les matchs depuis la BDD."""
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                nba_game_id, game_date, game_time,
                home_team_code, away_team_code,
                status, home_score, away_score, arena
            FROM games_schedule
            WHERE game_date >= CURRENT_DATE 
            AND game_date <= CURRENT_DATE + INTERVAL '7 days'
            ORDER BY game_date, game_time
        """)

        games = []
        for row in cur.fetchall():
            games.append({
                'nba_game_id': row[0],
                'game_date': row[1].isoformat() if row[1] else None,
                'game_time': row[2],
                'home_team': row[3],
                'away_team': row[4],
                'status': row[5],
                'home_score': row[6],
                'away_score': row[7],
                'arena': row[8]
            })

        cur.close()
        conn.close()

        return games

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return []


if __name__ == "__main__":
    print("=" * 80)
    print("🏀 TEST DU MODULE WEEKLY_GAMES (HTTP)")
    print("=" * 80)

    result = sync_weekly_games(force_refresh=True)
    print(f"\nRésultat: {result}")

    games = get_weekly_games_from_db()
    print(f"\n✅ {len(games)} matchs en BDD")

    for game in games[:5]:
        print(f"   {game['game_date']} - {game['away_team']} @ {game['home_team']}")
