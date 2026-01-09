#!/usr/bin/env python3
"""Script de debug pour identifier pourquoi 0 picks"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy.orm import Session
from backend.database import engine
from backend import models
from datetime import datetime

print("🔍 DEBUG: Analyse des joueurs et stats")
print("=" * 80)

with Session(engine) as db:
    # 1. Compter les joueurs en BDD
    total_players = db.query(models.Player).count()
    print(f"✅ Joueurs en BDD: {total_players}")

    # 2. Compter les stats
    total_stats = db.query(models.PlayerGameStats).count()
    print(f"✅ Stats en BDD: {total_stats}")

    # 3. Matchs du jour
    today = datetime.now().date()
    games_today = db.query(models.GameSchedule).filter(models.GameSchedule.game_date == today).all()
    print(f"✅ Matchs aujourd'hui: {len(games_today)}")

    if not games_today:
        print("⚠️ Aucun match aujourd'hui, on prend le premier match disponible")
        games_today = db.query(models.GameSchedule).limit(1).all()

    if games_today:
        game = games_today[0]
        print(f"\n🏀 Test sur match: {game.away_team_code} @ {game.home_team_code} ({game.nba_game_id})")

        # 4. Simuler get_roster
        from backend.main import get_roster_for_team
        home_roster = get_roster_for_team(game.home_team_code, db)
        away_roster = get_roster_for_team(game.away_team_code, db)
        all_players = home_roster + away_roster

        print(f"📊 Total joueurs récupérés: {len(all_players)}")

        # 5. Compter combien ont un ID
        with_id = [p for p in all_players if p.get('id')]
        without_id = [p for p in all_players if not p.get('id')]

        print(f"✅ Avec ID: {len(with_id)}")
        print(f"❌ Sans ID: {len(without_id)}")

        if without_id:
            print("\n⚠️ Exemples de joueurs SANS ID:")
            for p in without_id[:5]:
                print(f"   - {p.get('full_name')} (nba_id={p.get('nba_id')})")

        # 6. Pour les joueurs avec ID, vérifier les stats
        if with_id:
            print(f"\n🔍 Test stats pour {len(with_id)} joueurs avec ID...")
            players_with_stats = 0
            players_without_stats = 0

            for p in with_id[:10]:  # Tester les 10 premiers
                stats_count = db.query(models.PlayerGameStats).filter(
                    models.PlayerGameStats.player_id == p['id']
                ).count()
                if stats_count > 0:
                    players_with_stats += 1
                    print(f"   ✅ {p['full_name']} (id={p['id']}): {stats_count} stats")
                else:
                    players_without_stats += 1
                    print(f"   ❌ {p['full_name']} (id={p['id']}): 0 stats")

            print(f"\n📊 Résumé (sur 10 testés):")
            print(f"   Avec stats: {players_with_stats}")
            print(f"   Sans stats: {players_without_stats}")

            # 7. Vérifier les snapshots
            snapshots = db.query(models.OddsSnapshot).filter(
                models.OddsSnapshot.game_id == game.nba_game_id
            ).count()
            print(f"\n💰 Snapshots pour ce match: {snapshots}")

print("\n" + "=" * 80)
print("✅ Debug terminé")

