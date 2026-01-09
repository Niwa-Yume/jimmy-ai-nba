#!/usr/bin/env python3
"""
🔍 Script de diagnostic rapide pour identifier pourquoi 0 picks sont détectés.
Usage: docker exec -it jimmy_backend python debug_0_picks.py
"""

import os
import sys
from pathlib import Path

# Ensure project root on PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from datetime import datetime, timedelta
from backend.database import SessionLocal
from backend import models
from backend.betting_service import BettingOddsProvider

def check_api_quota():
    """Vérifie l'état du quota API."""
    print("=" * 80)
    print("🔑 ÉTAPE 1 : Vérification des clés API The-Odds-API")
    print("=" * 80)

    provider = BettingOddsProvider()

    if not provider.api_keys:
        print("❌ AUCUNE CLÉ API TROUVÉE")
        print("   💡 Solution : Ajoutez THE_ODDS_API_KEY dans le fichier .env")
        print("   📖 Documentation : https://the-odds-api.com")
        return False

    print(f"✅ {len(provider.api_keys)} clé(s) disponible(s)")
    print(f"   📡 Clé active : {provider.api_key[:6]}*** ({provider.current_key_index + 1}/{len(provider.api_keys)})")

    if provider.quota_exceeded:
        print("❌ QUOTA DÉPASSÉ pour la clé actuelle")
        return False

    print("✅ Quota API OK\n")
    return True


def check_odds_in_db():
    """Vérifie les cotes présentes en BDD."""
    print("=" * 80)
    print("📊 ÉTAPE 2 : Vérification des cotes en base de données")
    print("=" * 80)

    with SessionLocal() as db:
        # Total cotes
        total_odds = db.query(models.OddsSnapshot).count()
        print(f"📈 Total cotes en BDD : {total_odds}")

        if total_odds == 0:
            print("❌ AUCUNE COTE EN BASE DE DONNÉES")
            print("   💡 Lancez : docker exec -it jimmy_backend python data-pipeline/fetch_odds_snapshots.py")
            return False

        # Cotes récentes (dernières 4h)
        recent_cutoff = datetime.utcnow() - timedelta(hours=4)
        recent_odds = db.query(models.OddsSnapshot).filter(
            models.OddsSnapshot.fetched_at >= recent_cutoff
        ).count()
        print(f"⏰ Cotes récentes (< 4h) : {recent_odds}")

        if recent_odds == 0:
            print("⚠️  Toutes les cotes sont obsolètes (> 4h)")
            print("   💡 Relancez un scan pour rafraîchir les cotes")

        # Répartition par marché
        market_counts = db.query(
            models.OddsSnapshot.market,
            models.func.count(models.OddsSnapshot.id)
        ).group_by(models.OddsSnapshot.market).all()

        print("\n📋 Répartition par marché :")
        for market, count in market_counts:
            print(f"   • {market}: {count} lignes")

        # Matchs avec cotes
        games_with_odds = db.query(models.OddsSnapshot.game_id).distinct().count()
        print(f"\n🏀 Matchs avec cotes : {games_with_odds}")

        print("✅ Cotes présentes en BDD\n")
        return True


def check_players_stats():
    """Vérifie les stats des joueurs."""
    print("=" * 80)
    print("👥 ÉTAPE 3 : Vérification des statistiques joueurs")
    print("=" * 80)

    with SessionLocal() as db:
        # Total joueurs
        total_players = db.query(models.Player).count()
        print(f"👤 Total joueurs en BDD : {total_players}")

        if total_players == 0:
            print("❌ AUCUN JOUEUR EN BASE DE DONNÉES")
            print("   💡 Lancez : docker exec -it jimmy_backend python data-pipeline/populate_players.py")
            return False

        # Joueurs avec stats récentes (saison en cours)
        season_start = datetime(2024, 10, 1)
        players_with_stats = db.query(models.PlayerGameStats.player_id).filter(
            models.PlayerGameStats.game_date >= season_start
        ).distinct().count()

        print(f"📊 Joueurs avec stats (saison 2024-25) : {players_with_stats}")

        if players_with_stats == 0:
            print("❌ AUCUNE STATISTIQUE POUR LA SAISON EN COURS")
            print("   💡 Lancez : docker exec -it jimmy_backend python data-pipeline/populate_stats.py")
            return False

        # Stats totales
        total_stats = db.query(models.PlayerGameStats).filter(
            models.PlayerGameStats.game_date >= season_start
        ).count()
        print(f"📈 Total stats (saison 2024-25) : {total_stats}")

        print("✅ Statistiques joueurs OK\n")
        return True


def check_games():
    """Vérifie les matchs programmés."""
    print("=" * 80)
    print("🏀 ÉTAPE 4 : Vérification des matchs programmés")
    print("=" * 80)

    with SessionLocal() as db:
        # Matchs aujourd'hui
        today = datetime.now().date()
        games_today = db.query(models.GameSchedule).filter(
            models.GameSchedule.game_date == today
        ).all()

        print(f"📅 Matchs aujourd'hui ({today}) : {len(games_today)}")

        if len(games_today) == 0:
            print("⚠️  Aucun match programmé aujourd'hui")
            print("   💡 Vérifiez la date ou synchronisez les matchs")
        else:
            print("\n📋 Liste des matchs :")
            for game in games_today:
                print(f"   • {game.away_team_code} @ {game.home_team_code} ({game.nba_game_id})")

        # Matchs avec cotes
        games_with_odds = [g.nba_game_id for g in games_today]
        if games_with_odds:
            odds_counts = db.query(
                models.OddsSnapshot.game_id,
                models.func.count(models.OddsSnapshot.id)
            ).filter(
                models.OddsSnapshot.game_id.in_(games_with_odds)
            ).group_by(models.OddsSnapshot.game_id).all()

            print(f"\n📊 Cotes disponibles par match :")
            for game_id, count in odds_counts:
                game = next((g for g in games_today if g.nba_game_id == game_id), None)
                if game:
                    print(f"   • {game.away_team_code} @ {game.home_team_code}: {count} lignes")

        print("\n✅ Matchs programmés OK\n")
        return True


def diagnose():
    """Diagnostic complet."""
    print("\n" + "=" * 80)
    print("🔍 DIAGNOSTIC COMPLET - Pourquoi 0 picks détectés ?")
    print("=" * 80 + "\n")

    checks = [
        ("API Quota", check_api_quota),
        ("Cotes en BDD", check_odds_in_db),
        ("Stats joueurs", check_players_stats),
        ("Matchs programmés", check_games),
    ]

    results = {}
    for name, check_func in checks:
        try:
            results[name] = check_func()
        except Exception as e:
            print(f"❌ ERREUR lors de la vérification '{name}': {e}")
            results[name] = False

    # Résumé
    print("=" * 80)
    print("📋 RÉSUMÉ DU DIAGNOSTIC")
    print("=" * 80)

    all_ok = all(results.values())
    for name, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"{status} {name}")

    print("\n" + "=" * 80)

    if all_ok:
        print("✅ TOUT EST CONFIGURÉ CORRECTEMENT")
        print("💡 Si vous avez toujours 0 picks, lancez un nouveau scan et regardez les logs détaillés")
    else:
        print("⚠️  PROBLÈMES DÉTECTÉS")
        print("💡 Suivez les instructions ci-dessus pour corriger les problèmes")

    print("=" * 80)


if __name__ == "__main__":
    try:
        diagnose()
    except KeyboardInterrupt:
        print("\n⚠️  Diagnostic interrompu")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERREUR FATALE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

