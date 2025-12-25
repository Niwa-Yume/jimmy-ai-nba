"""
Module de synchronisation des blessures NBA (version optimisée ESPN).
Utilise l'endpoint agrégé ESPN pour récupérer toutes les blessures en une fois.
"""

import psycopg2
import requests
from datetime import datetime, timedelta

DB_PARAMS = {
    "dbname": "jimmy_nba_db",
    "user": "jimmy_user",
    "password": "secure_password_123",
    "host": "localhost",
    "port": "5432"
}

STATUS_PROBABILITY = {
    'OUT': 0,
    'DOUBTFUL': 25,
    'QUESTIONABLE': 50,
    'PROBABLE': 75,
    'DAY_TO_DAY': 50,
    'GTD': 50,
    'HEALTHY': 100,
    'ACTIVE': 100
}


def fetch_espn_injuries_simple():
    """Récupère toutes les blessures ESPN en une requête."""
    print("🏥 Récupération des blessures depuis ESPN (endpoint agrégé)...")

    injuries = []

    try:
        # Endpoint agrégé ESPN (plus rapide)
        url = "https://site.web.api.espn.com/apis/fantasy/v2/games/fba/seasons/2025/segments/0/leagues/default?view=kona_player_info"

        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            'Referer': 'https://fantasy.espn.com/'
        }

        response = requests.get(url, headers=headers, timeout=15)

        if not response.ok:
            # Fallback : essayer l'ancien endpoint
            print("   Tentative endpoint alternatif...")
            url = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/teams"
            response = requests.get(url, headers=headers, timeout=15)

        if response.ok:
            data = response.json()

            # Parser les données (structure varie selon l'endpoint)
            players_data = data.get('players', [])

            if not players_data and 'sports' in data:
                # Format alternatif
                print("   Format de données alternatif détecté")
                return []

            for player in players_data:
                # Extraire les infos de blessure
                injury_status = player.get('injuryStatus', 'ACTIVE')

                if injury_status and injury_status != 'ACTIVE':
                    injuries.append({
                        'espn_player_id': player.get('id'),
                        'player_name': player.get('fullName', player.get('lastName', 'Unknown')),
                        'status': injury_status.upper(),
                        'injury_type': player.get('injury', {}).get('type'),
                        'injury_detail': player.get('injury', {}).get('details'),
                        'source': 'ESPN'
                    })

        print(f"✅ {len(injuries)} blessures trouvées")
        return injuries

    except Exception as e:
        print(f"⚠️ Erreur ESPN : {e}")
        return []


def map_player_name(name, conn):
    """Mappe un nom vers un player_id en BDD (fuzzy match)."""
    cur = conn.cursor()

    # Nettoyage du nom
    search_name = name.upper().strip()

    # Recherche exacte
    cur.execute("""
        SELECT id, nba_player_id 
        FROM player 
        WHERE UPPER(full_name) = %s 
        LIMIT 1
    """, (search_name,))

    result = cur.fetchone()

    if result:
        cur.close()
        return result[0], result[1]

    # Recherche partielle (LIKE)
    parts = search_name.split()
    if len(parts) >= 2:
        last_name = parts[-1]
        cur.execute("""
            SELECT id, nba_player_id 
            FROM player 
            WHERE UPPER(full_name) LIKE %s
            LIMIT 1
        """, (f"%{last_name}%",))

        result = cur.fetchone()
        if result:
            cur.close()
            return result[0], result[1]

    cur.close()
    return None, None


def sync_injuries(force_refresh=False):
    """Synchronise les blessures en BDD."""
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        # Vérifier cache
        if not force_refresh:
            cur.execute("""
                SELECT MAX(last_verified_at) 
                FROM player_injuries 
                WHERE is_active = TRUE
            """)
            last_check = cur.fetchone()[0]

            if last_check:
                time_since = datetime.now() - last_check
                if time_since < timedelta(hours=2):
                    cur.execute("SELECT COUNT(*) FROM player_injuries WHERE is_active = TRUE")
                    cached = cur.fetchone()[0]
                    print(f"📦 Cache valide : {cached} blessures actives")
                    cur.close()
                    conn.close()
                    return {"new": 0, "updated": 0, "resolved": 0, "cached": cached}

        # Fetch injuries
        injuries = fetch_espn_injuries_simple()

        if not injuries:
            print("⚠️ Aucune blessure récupérée, on garde les données existantes")
            cur.close()
            conn.close()
            return {"new": 0, "updated": 0, "resolved": 0, "cached": 0}

        new_count = 0
        updated_count = 0
        resolved_count = 0
        current_injured = set()

        for injury in injuries:
            player_name = injury.get('player_name')
            status = injury.get('status', 'UNKNOWN')

            if not player_name:
                continue

            # Mapper au joueur en BDD
            player_id, nba_player_id = map_player_name(player_name, conn)

            if not player_id:
                continue

            current_injured.add(player_id)

            # Probabilité de jouer
            play_prob = STATUS_PROBABILITY.get(status, 50)

            # Vérifier si existe
            cur.execute("""
                SELECT id, status 
                FROM player_injuries 
                WHERE player_id = %s AND is_active = TRUE
                LIMIT 1
            """, (player_id,))

            existing = cur.fetchone()

            if existing:
                old_status = existing[1]

                if status != old_status:
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
                    print(f"   🔄 {player_name} - {status}")
                else:
                    # Juste màj timestamp
                    cur.execute("""
                        UPDATE player_injuries 
                        SET last_verified_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (existing[0],))
            else:
                # Insert nouveau
                cur.execute("""
                    INSERT INTO player_injuries 
                    (player_id, nba_player_id, status, injury_type, injury_detail,
                     injury_date, play_probability, source, is_active)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_DATE, %s, %s, TRUE)
                """, (
                    player_id, nba_player_id, status,
                    injury.get('injury_type'), injury.get('injury_detail'),
                    play_prob, 'ESPN'
                ))

                new_count += 1
                print(f"   ✨ {player_name} - {status}")

            # Màj table player
            cur.execute("""
                UPDATE player 
                SET current_injury_status = %s,
                    injury_updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
            """, (status, player_id))

        # Résoudre les blessures guéries
        cur.execute("""
            SELECT id, player_id 
            FROM player_injuries 
            WHERE is_active = TRUE
        """)

        for injury_id, player_id in cur.fetchall():
            if player_id not in current_injured:
                cur.execute("""
                    UPDATE player_injuries 
                    SET is_active = FALSE,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (injury_id,))

                cur.execute("""
                    UPDATE player 
                    SET current_injury_status = 'HEALTHY',
                        injury_updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                """, (player_id,))

                resolved_count += 1

        conn.commit()

        print(f"\n🎉 Sync blessures terminée !")
        print(f"   {new_count} nouvelles, {updated_count} màj, {resolved_count} résolues")

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
    """Récupère les blessures actives depuis BDD."""
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        cur.execute("""
            SELECT 
                p.full_name,
                pi.status,
                pi.injury_type,
                pi.injury_detail,
                pi.play_probability
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
                'play_probability': row[4]
            })

        cur.close()
        conn.close()

        return injuries

    except Exception as e:
        print(f"❌ Erreur : {e}")
        return []


if __name__ == "__main__":
    print("=" * 80)
    print("🏥 TEST MODULE INJURIES (OPTIMISÉ)")
    print("=" * 80)

    result = sync_injuries(force_refresh=True)
    print(f"\nRésultat: {result}")

    injuries = get_active_injuries_from_db()
    print(f"\n✅ {len(injuries)} blessures actives")

    for injury in injuries[:15]:
        prob = f"{injury['play_probability']}%" if injury['play_probability'] else "N/A"
        print(f"   {injury['player']} - {injury['status']} ({prob})")
