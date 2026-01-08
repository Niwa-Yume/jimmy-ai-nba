#!/usr/bin/env python3
"""
Script d'initialisation de la base de données en production.

🚀 À exécuter une fois au premier démarrage du VPS :
   docker compose exec backend python /app/data-pipeline/init_db_prod.py

📋 Étapes :
1. Vérifie que la DB est accessible
2. Synchronise les matchs de la semaine
3. Peuple la table players
4. Récupère les blessures actives
5. Affiche un résumé
"""

import sys
import time
import os

# Import des modules de synchronisation
try:
    from sync_weekly_games_v2 import sync_weekly_games
    from populate_players import populate_all_players
    from sync_injuries import sync_injuries
except ImportError:
    # Si on est dans data-pipeline/, ajouter le path parent
    sys.path.insert(0, os.path.dirname(__file__))
    from sync_weekly_games_v2 import sync_weekly_games
    from populate_players import populate_all_players
    from sync_injuries import sync_injuries

import psycopg2

DB_PARAMS = {
    "dbname": os.getenv("DB_NAME", "jimmy_nba_db"),
    "user": os.getenv("DB_USER", "jimmy_user"),
    "password": os.getenv("DB_PASSWORD", "secure_password_123"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}


def test_db_connection(max_retries=5):
    """Test la connexion à la base de données avec retry."""
    print("🔌 Test de connexion à la base de données...")

    for attempt in range(1, max_retries + 1):
        try:
            conn = psycopg2.connect(**DB_PARAMS)
            conn.close()
            print(f"   ✅ Connexion établie (tentative {attempt}/{max_retries})")
            return True
        except Exception as e:
            print(f"   ⚠️ Tentative {attempt}/{max_retries} échouée : {e}")
            if attempt < max_retries:
                time.sleep(2)
            else:
                return False

    return False


def main():
    print("=" * 80)
    print("🚀 INITIALISATION DE LA BASE DE DONNÉES (PRODUCTION)")
    print("=" * 80)

    # Étape 1 : Test connexion
    if not test_db_connection():
        print("\n❌ Impossible de se connecter à la base de données")
        print("   Vérifier que le conteneur 'db' est démarré")
        sys.exit(1)

    # Étape 2 : Synchroniser les matchs
    print("\n📅 Étape 2/4 : Synchronisation des matchs de la semaine")
    print("-" * 80)
    try:
        result = sync_weekly_games(force_refresh=True)
        print(f"   ✅ {result['new']} nouveaux matchs, {result['updated']} mis à jour")
    except Exception as e:
        print(f"   ⚠️ Erreur : {e}")

    # Étape 3 : Peupler les joueurs
    print("\n👥 Étape 3/4 : Peuplement de la table players")
    print("-" * 80)
    try:
        result = populate_all_players()
        print(f"   ✅ {result['new']} nouveaux joueurs, {result['updated']} mis à jour")
    except Exception as e:
        print(f"   ⚠️ Erreur : {e}")

    # Étape 4 : Synchroniser les blessures
    print("\n🏥 Étape 4/4 : Synchronisation des blessures")
    print("-" * 80)
    try:
        result = sync_injuries(force_refresh=True)
        print(f"   ✅ {result['new']} nouvelles blessures, {result['updated']} mises à jour")
    except Exception as e:
        print(f"   ⚠️ Erreur : {e}")

    # Résumé final
    print("\n" + "=" * 80)
    print("📊 RÉSUMÉ - État de la base de données")
    print("=" * 80)

    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()

        # Matchs
        cur.execute("SELECT COUNT(*) FROM games_schedule WHERE game_date >= CURRENT_DATE")
        games_count = cur.fetchone()[0]
        print(f"   🏀 Matchs à venir : {games_count}")

        # Joueurs
        cur.execute("SELECT COUNT(*) FROM player")
        players_count = cur.fetchone()[0]
        print(f"   👤 Joueurs référencés : {players_count}")

        # Blessures actives
        cur.execute("SELECT COUNT(*) FROM player_injuries WHERE is_active = TRUE")
        injuries_count = cur.fetchone()[0]
        print(f"   🏥 Blessures actives : {injuries_count}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"   ⚠️ Impossible de récupérer le résumé : {e}")

    print("\n" + "=" * 80)
    print("✅ Initialisation terminée !")
    print("=" * 80)
    print("\n💡 Le backend est prêt à démarrer le scan")
    print("   → Accède au frontend sur http://jimmyainba.duckdns.org\n")


if __name__ == "__main__":
    main()

