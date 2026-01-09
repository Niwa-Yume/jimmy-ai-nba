#!/usr/bin/env python3
"""
🧪 Test rapide de l'API The-Odds pour vérifier le quota et les matchs disponibles.
Usage: python test_odds_api.py
"""

import os
import sys
import requests
from pathlib import Path
from dotenv import load_dotenv

# Load .env
ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=ROOT_DIR / '.env')

def test_api():
    """Test l'API The-Odds."""
    print("=" * 80)
    print("🧪 TEST DE L'API THE-ODDS-API")
    print("=" * 80 + "\n")

    # Récupérer les clés
    api_keys_str = os.getenv('THE_ODDS_API_KEY', '')
    if not api_keys_str:
        print("❌ ERREUR: Aucune clé API trouvée dans .env")
        print("   💡 Ajoutez THE_ODDS_API_KEY dans le fichier .env")
        return False

    api_keys = [k.strip() for k in api_keys_str.split(',') if k.strip()]
    print(f"🔑 {len(api_keys)} clé(s) trouvée(s) dans .env")

    base_url = "https://api.the-odds-api.com/v4"

    for i, key in enumerate(api_keys, 1):
        print(f"\n{'=' * 80}")
        print(f"🔑 TEST CLÉ #{i}: {key[:6]}***")
        print("=" * 80)

        # Test 1: Quota check
        print("\n📊 Test 1/3 : Vérification du quota...")
        try:
            res = requests.get(
                f"{base_url}/sports/basketball_nba/odds",
                params={"apiKey": key, "regions": "us", "markets": "h2h"},
                timeout=5
            )

            # Quota restant
            remaining = res.headers.get('x-requests-remaining', 'N/A')
            used = res.headers.get('x-requests-used', 'N/A')

            if res.status_code == 200:
                print(f"✅ Quota restant: {remaining}")
                print(f"   📈 Requêtes utilisées: {used}")
            elif res.status_code == 401:
                print(f"❌ CLÉ INVALIDE (HTTP 401)")
                continue
            elif res.status_code == 429:
                print(f"❌ QUOTA DÉPASSÉ (HTTP 429)")
                print(f"   📈 Requêtes utilisées: {used}")
                continue
            else:
                print(f"⚠️  Erreur HTTP {res.status_code}")
                continue

        except Exception as e:
            print(f"❌ ERREUR: {e}")
            continue

        # Test 2: Liste des matchs
        print("\n🏀 Test 2/3 : Matchs NBA disponibles...")
        try:
            events = res.json()
            print(f"✅ {len(events)} matchs trouvés")

            if len(events) > 0:
                print("\n📋 Premiers matchs :")
                for event in events[:5]:
                    home = event.get('home_team', 'N/A')
                    away = event.get('away_team', 'N/A')
                    date = event.get('commence_time', 'N/A')
                    print(f"   • {away} @ {home} ({date})")
            else:
                print("⚠️  Aucun match disponible actuellement")

        except Exception as e:
            print(f"❌ ERREUR: {e}")
            continue

        # Test 3: Cotes joueur
        print("\n👤 Test 3/3 : Cotes joueur disponibles...")
        if len(events) > 0:
            event_id = events[0]['id']
            try:
                # Test avec TOUS les marchés possibles
                all_markets = "player_points,player_rebounds,player_assists,player_threes,player_three_points_made,player_threes_made"
                res = requests.get(
                    f"{base_url}/sports/basketball_nba/events/{event_id}/odds",
                    params={
                        "apiKey": key,
                        "regions": "us",
                        "markets": all_markets,
                        "oddsFormat": "decimal"
                    },
                    timeout=5
                )

                if res.status_code == 200:
                    data = res.json()
                    bookmakers = data.get('bookmakers', [])
                    print(f"✅ {len(bookmakers)} bookmaker(s) disponible(s)")

                    if bookmakers:
                        bookie = bookmakers[0]
                        print(f"   📚 Bookmaker: {bookie.get('title')}")
                        markets = bookie.get('markets', [])
                        print(f"   🏷️  Markets: {len(markets)}")

                        for market in markets[:3]:
                            m_key = market.get('key', 'N/A')
                            outcomes = len(market.get('outcomes', []))
                            print(f"      • {m_key}: {outcomes} joueurs")
                    else:
                        print("⚠️  Aucune cote joueur disponible pour ce match")
                else:
                    print(f"⚠️  Erreur HTTP {res.status_code}")

            except Exception as e:
                print(f"❌ ERREUR: {e}")

        print(f"\n✅ CLÉ #{i} TESTÉE AVEC SUCCÈS")
        return True

    print("\n" + "=" * 80)
    print("❌ TOUTES LES CLÉS SONT INVALIDES OU ÉPUISÉES")
    print("=" * 80)
    return False


if __name__ == "__main__":
    try:
        success = test_api()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrompu")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERREUR FATALE: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

