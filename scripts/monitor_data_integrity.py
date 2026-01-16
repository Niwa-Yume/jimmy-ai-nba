#!/usr/bin/env python3
"""
Script de monitoring de l'intégrité des données.
Vérifie la cohérence entre les projections, les lignes bookmaker et les paris générés.
"""

import sys
import os
from pathlib import Path

# Ajouter le répertoire parent au path pour importer les modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from backend.database import SessionLocal
from backend import models
from sqlalchemy import func, desc
from datetime import datetime, timedelta


def check_over_under_consistency():
    """Vérifie que tous les picks ont la bonne direction Over/Under"""
    print("\n" + "="*70)
    print("🔍 VÉRIFICATION DE LA COHÉRENCE OVER/UNDER")
    print("="*70 + "\n")

    db = SessionLocal()
    try:
        # Récupérer les snapshots récents (dernières 24h)
        since = datetime.utcnow() - timedelta(hours=24)
        snapshots = db.query(models.OddsSnapshot).filter(
            models.OddsSnapshot.created_at >= since
        ).all()

        if not snapshots:
            print("⚠️ Aucun snapshot trouvé dans les dernières 24h")
            return

        print(f"📊 Analyse de {len(snapshots)} snapshots récents...\n")

        issues = []
        for snap in snapshots:
            # Vérifier chaque marché
            for market in ['points', 'rebounds', 'assists']:
                over_line = getattr(snap, f'{market}_over_line', None)
                under_line = getattr(snap, f'{market}_under_line', None)

                if over_line and under_line:
                    # Les lignes over/under devraient être identiques
                    if over_line != under_line:
                        issues.append({
                            'player_id': snap.player_id,
                            'game_id': snap.game_id,
                            'market': market,
                            'over_line': over_line,
                            'under_line': under_line,
                            'issue': 'LIGNES_DIFFÉRENTES'
                        })

        if issues:
            print(f"⚠️ {len(issues)} incohérences détectées:\n")
            for issue in issues[:10]:  # Afficher les 10 premières
                print(f"   • Joueur {issue['player_id']}, Marché {issue['market']}")
                print(f"     Ligne Over: {issue['over_line']}, Ligne Under: {issue['under_line']}")
        else:
            print("✅ Aucune incohérence détectée dans les lignes Over/Under")

    finally:
        db.close()


def check_odds_freshness():
    """Vérifie la fraîcheur des cotes (évite d'utiliser des données trop anciennes)"""
    print("\n" + "="*70)
    print("🔍 VÉRIFICATION DE LA FRAÎCHEUR DES COTES")
    print("="*70 + "\n")

    db = SessionLocal()
    try:
        # Compter les snapshots par âge
        now = datetime.utcnow()

        counts = {
            'moins_1h': 0,
            '1h_4h': 0,
            '4h_24h': 0,
            'plus_24h': 0
        }

        snapshots = db.query(models.OddsSnapshot).all()

        for snap in snapshots:
            age_hours = (now - snap.created_at).total_seconds() / 3600

            if age_hours < 1:
                counts['moins_1h'] += 1
            elif age_hours < 4:
                counts['1h_4h'] += 1
            elif age_hours < 24:
                counts['4h_24h'] += 1
            else:
                counts['plus_24h'] += 1

        total = sum(counts.values())

        if total == 0:
            print("⚠️ Aucun snapshot en base de données")
            return

        print(f"📊 Distribution de l'âge des cotes (total: {total}):\n")
        print(f"   • < 1 heure:    {counts['moins_1h']:4d} ({counts['moins_1h']/total*100:.1f}%)")
        print(f"   • 1-4 heures:   {counts['1h_4h']:4d} ({counts['1h_4h']/total*100:.1f}%)")
        print(f"   • 4-24 heures:  {counts['4h_24h']:4d} ({counts['4h_24h']/total*100:.1f}%)")
        print(f"   • > 24 heures:  {counts['plus_24h']:4d} ({counts['plus_24h']/total*100:.1f}%)")

        if counts['plus_24h'] > total * 0.5:
            print("\n⚠️ ALERTE: Plus de 50% des cotes ont plus de 24h")
            print("   💡 Lancez un scan pour rafraîchir les données")
        elif counts['moins_1h'] > total * 0.3:
            print("\n✅ Excellent: Plus de 30% des cotes sont très récentes (<1h)")
        else:
            print("\n⚠️ Les cotes ne sont pas très récentes, pensez à lancer un scan")

    finally:
        db.close()


def check_api_key_rotation():
    """Vérifie que le système utilise bien plusieurs clés API"""
    print("\n" + "="*70)
    print("🔍 VÉRIFICATION DE LA ROTATION DES CLÉS API")
    print("="*70 + "\n")

    keys_str = os.getenv('THE_ODDS_API_KEY', '')
    api_keys = [k.strip() for k in keys_str.split(',') if k.strip()]

    print(f"📊 {len(api_keys)} clé(s) API configurée(s)\n")

    if len(api_keys) == 0:
        print("❌ ERREUR: Aucune clé API configurée")
        return
    elif len(api_keys) == 1:
        print("⚠️ ATTENTION: Une seule clé API configurée")
        print("   💡 Ajoutez plusieurs clés pour éviter les limites de quota")
    else:
        print(f"✅ Bonne configuration: {len(api_keys)} clés disponibles pour la rotation")

    # Afficher les clés masquées
    for i, key in enumerate(api_keys, 1):
        masked = key[:4] + "***" + (key[-4:] if len(key) > 8 else "")
        print(f"   • Clé {i}: {masked}")


def check_projection_quality():
    """Vérifie la qualité des projections (évite les projections aberrantes)"""
    print("\n" + "="*70)
    print("🔍 VÉRIFICATION DE LA QUALITÉ DES PROJECTIONS")
    print("="*70 + "\n")

    db = SessionLocal()
    try:
        # Récupérer les stats récentes
        since = datetime.utcnow() - timedelta(days=7)

        # Compter les joueurs avec des stats récentes
        active_players = db.query(models.PlayerGameStats.player_id).filter(
            models.PlayerGameStats.game_date >= since
        ).distinct().count()

        print(f"📊 {active_players} joueurs actifs dans les 7 derniers jours\n")

        # Vérifier les stats aberrantes
        max_reasonable = {
            'points': 60,      # Max raisonnable: 60 points
            'rebounds': 30,    # Max raisonnable: 30 rebonds
            'assists': 20      # Max raisonnable: 20 passes
        }

        issues = []
        stats = db.query(models.PlayerGameStats).filter(
            models.PlayerGameStats.game_date >= since
        ).all()

        for stat in stats:
            if stat.points and stat.points > max_reasonable['points']:
                issues.append(f"Points aberrants: {stat.points} pour joueur {stat.player_id}")
            if stat.rebounds and stat.rebounds > max_reasonable['rebounds']:
                issues.append(f"Rebonds aberrants: {stat.rebounds} pour joueur {stat.player_id}")
            if stat.assists and stat.assists > max_reasonable['assists']:
                issues.append(f"Passes aberrantes: {stat.assists} pour joueur {stat.player_id}")

        if issues:
            print(f"⚠️ {len(issues)} statistiques aberrantes détectées:\n")
            for issue in issues[:10]:
                print(f"   • {issue}")
        else:
            print("✅ Aucune statistique aberrante détectée")

        if active_players < 100:
            print("\n⚠️ ATTENTION: Peu de joueurs actifs dans la base")
            print("   💡 Synchronisez les données avec: python data-pipeline/populate_stats.py")

    finally:
        db.close()


def main():
    print("\n" + "="*70)
    print("🛡️ MONITORING DE L'INTÉGRITÉ DES DONNÉES JIMMY AI")
    print("="*70)
    print(f"📅 Exécuté le: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    try:
        check_over_under_consistency()
        check_odds_freshness()
        check_api_key_rotation()
        check_projection_quality()

        print("\n" + "="*70)
        print("✅ MONITORING TERMINÉ")
        print("="*70 + "\n")

    except Exception as e:
        print(f"\n❌ ERREUR LORS DU MONITORING: {e}\n")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    exit(main())

