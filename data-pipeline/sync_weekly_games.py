"""
Module de synchronisation des matchs NBA de la semaine.

🏀 Fonctionnalités
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Récupère les matchs des 7 prochains jours via nba_api
- Cache intelligent : ne re-fetch que si > 6h depuis dernière màj
- Persistance en BDD (table games_schedule)
- Détection automatique des doublons
- Mise à jour des scores pour matchs en cours/terminés

Source : nba_api (officiel NBA.com)
"""

import psycopg2
from datetime import datetime, timedelta
from nba_api.live.nba.endpoints.scoreboard import ScoreBoard
from nba_api.stats.endpoints import leaguegamefinder
import time

# Configuration BDD
DB_PARAMS = {
    "dbname": "jimmy_nba_db",
    "user": "jimmy_user",
    "password": "secure_password_123",
    "host": "localhost",
    "port": "5432"
}

# Mapping team_id → team_code (codes à 3 lettres)
NBA_TEAM_CODES = {
    1610612737: "ATL", 1610612738: "BOS", 1610612739: "CLE", 1610612740: "NOP",
    1610612741: "CHI", 1610612742: "DAL", 1610612743: "DEN", 1610612744: "GSW",
    1610612745: "HOU", 1610612746: "LAC", 1610612747: "LAL", 1610612748: "MIA",
    1610612749: "MIL", 1610612750: "MIN", 1610612751: "BKN", 1610612752: "NYK",
    1610612753: "ORL", 1610612754: "IND", 1610612755: "PHI", 1610612756: "PHX",
    1610612757: "POR", 1610612758: "SAC", 1610612759: "SAS", 1610612760: "OKC",
    1610612761: "TOR", 1610612762: "UTA", 1610612763: "MEM", 1610612764: "WAS",
    1610612765: "DET", 1610612766: "CHA"
}


def needs_refresh(conn):
    """
    Vérifie si on doit re-fetch les matchs (cache > 6h).

    Returns:
        bool: True si on doit refresh
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT MAX(last_fetched_at) 
        FROM games_schedule 
        WHERE game_date >= CURRENT_DATE
    """)
    last_fetch = cur.fetchone()[0]
    cur.close()

    if not last_fetch:
        return True

    # Refresh si > 6 heures
    time_since_fetch = datetime.now() - last_fetch
    return time_since_fetch > timedelta(hours=6)


def fetch_weekly_games():
    """
    Récupère les matchs des 7 prochains jours depuis NBA.com.

    Returns:
        list: Liste de dicts avec les infos des matchs
    """
    print("🏀 Récupération des matchs de la semaine via NBA API...")

    games = []

    try:
        # Méthode 1 : ScoreBoard (matchs du jour + prochains jours)
        board = ScoreBoard()
        scoreboard_data = board.get_dict()

        if 'scoreboard' in scoreboard_data and 'games' in scoreboard_data['scoreboard']:
            for game in scoreboard_data['scoreboard']['games']:
                game_date_str = game.get('gameDateTimeUTC', '')[:10]  # Format: "2024-12-21T..."

                # Parser la date
                try:
                    game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()
                except:
                    continue

                # Filtrer : seulement les 7 prochains jours
                if game_date < datetime.now().date():
                    continue
                if game_date > datetime.now().date() + timedelta(days=7):
                    continue

                home_team = game.get('homeTeam', {})
                away_team = game.get('awayTeam', {})

                games.append({
                    'nba_game_id': game.get('gameId'),
                    'game_date': game_date,
                    'game_time': game.get('gameTimeUTC', '')[-8:-3] if game.get('gameTimeUTC') else None,  # "19:30"
                    'home_team_code': home_team.get('teamTricode'),
                    'away_team_code': away_team.get('teamTricode'),
                    'home_team_id': home_team.get('teamId'),
                    'away_team_id': away_team.get('teamId'),
                    'status': game.get('gameStatus', 1),  # 1=scheduled, 2=live, 3=final
                    'home_score': home_team.get('score'),
                    'away_score': away_team.get('score'),
                    'arena': game.get('arenaName'),
                })

        print(f"✅ {len(games)} matchs trouvés")
        return games

    except Exception as e:
        print(f"⚠️ Erreur lors de la récupération des matchs : {e}")
        return []


def sync_weekly_games(force_refresh=False):
    """
    Synchronise les matchs de la semaine en BDD avec cache intelligent.

    Args:
        force_refresh (bool): Forcer le refresh même si cache valide

    Returns:
        dict: {"new": int, "updated": int, "cached": int}
    """
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        # Vérifier si on doit refresh
        if not force_refresh and not needs_refresh(conn):
            # Compter les matchs en cache
            cur.execute("""
                SELECT COUNT(*) FROM games_schedule 
                WHERE game_date >= CURRENT_DATE 
                AND game_date <= CURRENT_DATE + INTERVAL '7 days'
            """)
            cached_count = cur.fetchone()[0]

            print(f"📦 Cache valide : {cached_count} matchs de la semaine déjà en BDD")
            cur.close()
            conn.close()
            return {"new": 0, "updated": 0, "cached": cached_count}

        # Fetch depuis l'API
        games = fetch_weekly_games()

        if not games:
            print("⚠️ Aucun match récupéré")
            cur.close()
            conn.close()
            return {"new": 0, "updated": 0, "cached": 0}

        new_count = 0
        updated_count = 0

        for game in games:
            # Convertir status (1/2/3 → SCHEDULED/LIVE/FINAL)
            status_map = {1: 'SCHEDULED', 2: 'LIVE', 3: 'FINAL'}
            status = status_map.get(game['status'], 'SCHEDULED')

            # Vérifier si le match existe
            cur.execute("""
                SELECT id, status, home_score, away_score 
                FROM games_schedule 
                WHERE nba_game_id = %s
            """, (game['nba_game_id'],))

            existing = cur.fetchone()

            if existing:
                # UPDATE si le statut ou les scores ont changé
                old_status, old_home, old_away = existing[1], existing[2], existing[3]

                if (status != old_status or
                    game['home_score'] != old_home or
                    game['away_score'] != old_away):

                    cur.execute("""
                        UPDATE games_schedule 
                        SET status = %s,
                            home_score = %s,
                            away_score = %s,
                            updated_at = CURRENT_TIMESTAMP,
                            last_fetched_at = CURRENT_TIMESTAMP
                        WHERE nba_game_id = %s
                    """, (status, game['home_score'], game['away_score'], game['nba_game_id']))

                    updated_count += 1
                    print(f"   🔄 MAJ: {game['away_team_code']} @ {game['home_team_code']} ({status})")
                else:
                    # Juste mettre à jour last_fetched_at
                    cur.execute("""
                        UPDATE games_schedule 
                        SET last_fetched_at = CURRENT_TIMESTAMP
                        WHERE nba_game_id = %s
                    """, (game['nba_game_id'],))
            else:
                # INSERT nouveau match
                cur.execute("""
                    INSERT INTO games_schedule 
                    (nba_game_id, game_date, game_time, home_team_code, away_team_code,
                     home_team_id, away_team_id, status, home_score, away_score, arena)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    game['nba_game_id'], game['game_date'], game['game_time'],
                    game['home_team_code'], game['away_team_code'],
                    game['home_team_id'], game['away_team_id'],
                    status, game['home_score'], game['away_score'], game['arena']
                ))

                new_count += 1
                print(f"   ✨ NOUVEAU: {game['away_team_code']} @ {game['home_team_code']} ({game['game_date']})")

        conn.commit()

        print(f"\n🎉 Synchronisation terminée !")
        print(f"   📊 {new_count} nouveaux matchs")
        print(f"   🔄 {updated_count} matchs mis à jour")

        cur.close()
        conn.close()

        return {"new": new_count, "updated": updated_count, "cached": 0}

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return {"new": 0, "updated": 0, "cached": 0}


def get_weekly_games_from_db():
    """
    Récupère les matchs de la semaine depuis la BDD.

    Returns:
        list: Liste des matchs avec toutes les infos
    """
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
        print(f"❌ Erreur lecture BDD : {e}")
        return []


if __name__ == "__main__":
    print("=" * 80)
    print("🏀 TEST DU MODULE WEEKLY_GAMES")
    print("=" * 80)

    # Test 1 : Synchronisation
    print("\n📥 Test 1 : Synchronisation des matchs")
    result = sync_weekly_games(force_refresh=True)
    print(f"Résultat : {result}")

    # Test 2 : Lecture depuis BDD
    print("\n📖 Test 2 : Lecture depuis BDD")
    games = get_weekly_games_from_db()

    print(f"\n✅ {len(games)} matchs de la semaine :")
    for game in games[:5]:  # Afficher les 5 premiers
        print(f"   {game['game_date']} {game['game_time']} - "
              f"{game['away_team']} @ {game['home_team']} ({game['status']})")

    print("\n" + "=" * 80)
