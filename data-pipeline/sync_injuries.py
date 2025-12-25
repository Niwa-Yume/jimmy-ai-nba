"""
Module de synchronisation des blessures NBA.

🏥 Fonctionnalités
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Récupère les injury reports depuis ESPN (source la plus fiable)
- Fallback sur NBA.com si ESPN indisponible
- Cache intelligent : refresh toutes les 2h
- Persistance en BDD (table player_injuries)
- Calcul automatique de play_probability selon le statut
- Historique des blessures (is_active flag)

Sources :
- Primaire : ESPN Injury Report API
- Secondaire : NBA.com Injury Report
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

# Mapping status → play_probability
STATUS_PROBABILITY = {
    'OUT': 0,
    'DOUBTFUL': 25,
    'QUESTIONABLE': 50,
    'PROBABLE': 75,
    'DAY_TO_DAY': 50,
    'GTD': 50,  # Game Time Decision
    'HEALTHY': 100,
    'ACTIVE': 100
}


def fetch_espn_injuries():
    """
    Récupère les blessures depuis l'API ESPN.

    Returns:
        list: Liste de dicts avec les infos de blessures
    """
    print("🏥 Récupération des blessures depuis ESPN...")

    injuries = []

    try:
        # ESPN Injury Report API (non officielle mais très utilisée)
        url = "https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/teams"

        response = requests.get(url, timeout=10)
        response.raise_for_status()

        teams_data = response.json()

        if 'sports' in teams_data and len(teams_data['sports']) > 0:
            teams = teams_data['sports'][0].get('leagues', [{}])[0].get('teams', [])

            for team_entry in teams:
                team = team_entry.get('team', {})
                team_id = team.get('id')
                team_abbr = team.get('abbreviation')

                # Récupérer le roster avec injuries
                roster_url = f"https://site.web.api.espn.com/apis/site/v2/sports/basketball/nba/teams/{team_id}/roster"

                try:
                    roster_response = requests.get(roster_url, timeout=5)
                    roster_response.raise_for_status()
                    roster_data = roster_response.json()

                    athletes = roster_data.get('athletes', [])

                    for athlete in athletes:
                        # Vérifier s'il y a une blessure
                        injuries_list = athlete.get('injuries', [])

                        if injuries_list:
                            for injury in injuries_list:
                                status = injury.get('status', 'UNKNOWN').upper()

                                # Extraire l'ID NBA du joueur
                                player_id = athlete.get('id')
                                player_name = athlete.get('displayName')

                                injuries.append({
                                    'espn_player_id': player_id,
                                    'player_name': player_name,
                                    'team': team_abbr,
                                    'status': status,
                                    'injury_type': injury.get('type'),
                                    'injury_detail': injury.get('details'),
                                    'date': injury.get('date'),
                                    'source': 'ESPN',
                                    'source_url': f"https://www.espn.com/nba/team/injuries/_/name/{team_abbr.lower()}"
                                })

                except Exception as e:
                    # Si une équipe échoue, continuer avec les autres
                    continue

        print(f"✅ {len(injuries)} blessures trouvées sur ESPN")
        return injuries

    except Exception as e:
        print(f"⚠️ Erreur ESPN : {e}")
        return []


def fetch_nba_injuries():
    """
    Récupère les blessures depuis NBA.com (fallback).

    Returns:
        list: Liste de dicts avec les infos de blessures
    """
    print("🏥 Récupération des blessures depuis NBA.com...")

    try:
        # Cette API est moins documentée, on essaie plusieurs endpoints
        url = "https://www.nba.com/stats/api/injuries/data"

        response = requests.get(url, timeout=10, headers={
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://www.nba.com/'
        })

        if response.ok:
            data = response.json()
            print(f"✅ {len(data.get('data', []))} blessures trouvées sur NBA.com")
            return data.get('data', [])
        else:
            return []

    except Exception as e:
        print(f"⚠️ Erreur NBA.com : {e}")
        return []


def map_espn_to_nba_player(espn_name, conn):
    """
    Mappe un nom ESPN vers un nba_player_id en BDD.

    Args:
        espn_name (str): Nom du joueur depuis ESPN
        conn: Connexion BDD

    Returns:
        tuple: (player_id, nba_player_id) ou (None, None)
    """
    cur = conn.cursor()

    # Recherche par nom (fuzzy match simple)
    # On enlève les accents et on met en majuscules
    search_name = espn_name.upper().strip()

    cur.execute("""
        SELECT id, nba_player_id 
        FROM player 
        WHERE UPPER(full_name) = %s 
        OR UPPER(full_name) LIKE %s
        LIMIT 1
    """, (search_name, f"%{search_name}%"))

    result = cur.fetchone()
    cur.close()

    if result:
        return result[0], result[1]

    return None, None


def needs_injury_refresh(conn):
    """
    Vérifie si on doit refresh les injuries (cache > 2h).

    Returns:
        bool: True si on doit refresh
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT MAX(last_verified_at) 
        FROM player_injuries 
        WHERE is_active = TRUE
    """)
    last_check = cur.fetchone()[0]
    cur.close()

    if not last_check:
        return True

    # Refresh si > 2 heures
    time_since_check = datetime.now() - last_check
    return time_since_check > timedelta(hours=2)


def sync_injuries(force_refresh=False):
    """
    Synchronise les blessures en BDD avec cache intelligent.

    Args:
        force_refresh (bool): Forcer le refresh même si cache valide

    Returns:
        dict: {"new": int, "updated": int, "resolved": int, "cached": int}
    """
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        # Vérifier si on doit refresh
        if not force_refresh and not needs_injury_refresh(conn):
            # Compter les blessures actives en cache
            cur.execute("SELECT COUNT(*) FROM player_injuries WHERE is_active = TRUE")
            cached_count = cur.fetchone()[0]

            print(f"📦 Cache valide : {cached_count} blessures actives déjà en BDD")
            cur.close()
            conn.close()
            return {"new": 0, "updated": 0, "resolved": 0, "cached": cached_count}

        # Fetch depuis ESPN (source principale)
        injuries = fetch_espn_injuries()

        # Si ESPN échoue, essayer NBA.com
        if not injuries:
            print("⚠️ ESPN indisponible, tentative NBA.com...")
            injuries = fetch_nba_injuries()

        if not injuries:
            print("❌ Aucune source disponible")
            cur.close()
            conn.close()
            return {"new": 0, "updated": 0, "resolved": 0, "cached": 0}

        new_count = 0
        updated_count = 0
        resolved_count = 0

        # Track les joueurs blessés actuellement
        current_injured_players = set()

        for injury in injuries:
            player_name = injury.get('player_name')
            status = injury.get('status', 'UNKNOWN')

            if not player_name:
                continue

            # Mapper au joueur en BDD
            player_id, nba_player_id = map_espn_to_nba_player(player_name, conn)

            if not player_id:
                print(f"   ⚠️ Joueur non trouvé en BDD : {player_name}")
                continue

            current_injured_players.add(player_id)

            # Calculer play_probability
            play_prob = STATUS_PROBABILITY.get(status, 50)

            # Vérifier si une blessure active existe
            cur.execute("""
                SELECT id, status, injury_type 
                FROM player_injuries 
                WHERE player_id = %s AND is_active = TRUE
                LIMIT 1
            """, (player_id,))

            existing = cur.fetchone()

            if existing:
                old_status, old_type = existing[1], existing[2]

                # UPDATE si le statut a changé
                if status != old_status or injury.get('injury_type') != old_type:
                    cur.execute("""
                        UPDATE player_injuries 
                        SET status = %s,
                            injury_type = %s,
                            injury_detail = %s,
                            play_probability = %s,
                            last_verified_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (status, injury.get('injury_type'), injury.get('injury_detail'),
                          play_prob, existing[0]))

                    updated_count += 1
                    print(f"   🔄 MAJ: {player_name} - {status}")
                else:
                    # Juste mettre à jour last_verified_at
                    cur.execute("""
                        UPDATE player_injuries 
                        SET last_verified_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (existing[0],))
            else:
                # INSERT nouvelle blessure
                cur.execute("""
                    INSERT INTO player_injuries 
                    (player_id, nba_player_id, status, injury_type, injury_detail,
                     injury_date, play_probability, source, source_url, is_active)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_DATE, %s, %s, %s, TRUE)
                """, (
                    player_id, nba_player_id, status,
                    injury.get('injury_type'), injury.get('injury_detail'),
                    play_prob, injury.get('source', 'ESPN'), injury.get('source_url')
                ))

                new_count += 1
                print(f"   ✨ NOUVEAU: {player_name} - {status} ({injury.get('injury_type')})")

            # Mettre à jour le statut dans la table player
            cur.execute("""
                UPDATE player 
                SET current_injury_status = %s,
                    injury_updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (status, player_id))

        # Marquer comme resolved les blessures qui ne sont plus dans l'API
        cur.execute("""
            SELECT id, player_id 
            FROM player_injuries 
            WHERE is_active = TRUE
        """)

        for injury_id, player_id in cur.fetchall():
            if player_id not in current_injured_players:
                cur.execute("""
                    UPDATE player_injuries 
                    SET is_active = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (injury_id,))

                # Mettre à jour player
                cur.execute("""
                    UPDATE player 
                    SET current_injury_status = 'HEALTHY',
                        injury_updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (player_id,))

                resolved_count += 1

        conn.commit()

        print(f"\n🎉 Synchronisation des blessures terminée !")
        print(f"   📊 {new_count} nouvelles blessures")
        print(f"   🔄 {updated_count} blessures mises à jour")
        print(f"   ✅ {resolved_count} blessures résolues")

        cur.close()
        conn.close()

        return {
            "new": new_count,
            "updated": updated_count,
            "resolved": resolved_count,
            "cached": 0
        }

    except Exception as e:
        print(f"❌ Erreur : {e}")
        import traceback
        traceback.print_exc()
        return {"new": 0, "updated": 0, "resolved": 0, "cached": 0}


def get_active_injuries_from_db():
    """
    Récupère les blessures actives depuis la BDD.

    Returns:
        list: Liste des blessures actives avec infos joueur
    """
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                p.full_name,
                pi.status,
                pi.injury_type,
                pi.injury_detail,
                pi.play_probability,
                pi.injury_date,
                pi.last_verified_at
            FROM player_injuries pi
            JOIN player p ON p.id = pi.player_id
            WHERE pi.is_active = TRUE
            ORDER BY pi.status, p.full_name
        """)

        injuries = []
        for row in cur.fetchall():
            injuries.append({
                'player': row[0],
                'status': row[1],
                'injury_type': row[2],
                'injury_detail': row[3],
                'play_probability': row[4],
                'injury_date': row[5].isoformat() if row[5] else None,
                'last_verified': row[6].isoformat() if row[6] else None
            })

        cur.close()
        conn.close()

        return injuries

    except Exception as e:
        print(f"❌ Erreur lecture BDD : {e}")
        return []


if __name__ == "__main__":
    print("=" * 80)
    print("🏥 TEST DU MODULE INJURIES")
    print("=" * 80)

    # Test 1 : Synchronisation
    print("\n📥 Test 1 : Synchronisation des blessures")
    result = sync_injuries(force_refresh=True)
    print(f"Résultat : {result}")

    # Test 2 : Lecture depuis BDD
    print("\n📖 Test 2 : Lecture depuis BDD")
    injuries = get_active_injuries_from_db()

    print(f"\n✅ {len(injuries)} blessures actives :")
    for injury in injuries[:10]:  # Afficher les 10 premiers
        prob = injury['play_probability']
        prob_str = f"{prob}%" if prob is not None else "N/A"
        print(f"   {injury['player']} - {injury['status']} - {injury['injury_type']} (Proba: {prob_str})")

    print("\n" + "=" * 80)
