#!/usr/bin/env python3
"""
Test pour vérifier que le scan fonctionne après correction du bug des marchés invalides
"""
import requests
import time

print("🧪 TEST DU SCAN APRÈS CORRECTION\n")

# 1. Vérifier que l'API backend est prête
print("1️⃣ Vérification de l'API backend...")
try:
    r = requests.get("http://localhost:8000/games/week", timeout=5)
    if r.status_code == 200:
        games = r.json()
        print(f"   ✅ Backend OK - {len(games)} matchs trouvés")
    else:
        print(f"   ❌ Backend erreur: HTTP {r.status_code}")
        exit(1)
except Exception as e:
    print(f"   ❌ Backend inaccessible: {e}")
    exit(1)

# 2. Lancer un scan
print("\n2️⃣ Lancement d'un scan...")
try:
    r = requests.post("http://localhost:8000/analysis/start-scan", timeout=10)
    if r.status_code == 200:
        data = r.json()
        scan_id = data.get("job_id")  # Correction: c'est job_id, pas scan_id
        print(f"   ✅ Scan lancé avec ID: {scan_id}")
    else:
        print(f"   ❌ Erreur scan: HTTP {r.status_code}")
        exit(1)
except Exception as e:
    print(f"   ❌ Erreur scan: {e}")
    exit(1)

# 3. Attendre et récupérer les résultats
print("\n3️⃣ Attente des résultats (60s max)...")
for i in range(60):
    time.sleep(1)
    try:
        r = requests.get(f"http://localhost:8000/analysis/scan-results/{scan_id}", timeout=5)
        if r.status_code == 200:
            results = r.json()
            status = results.get("status")

            if status == "completed":
                picks = results.get("picks", [])
                counters = results.get("debug_counters", {})

                print(f"\n✅ SCAN TERMINÉ !")
                print(f"   📊 Total vérifié: {counters.get('total_checked', 0)}")
                print(f"   🎯 Picks potentiels: {counters.get('potential', 0)}")
                print(f"   ⭐ Picks sélectionnés: {len(picks)}")

                # Détails par marché
                no_line_by_market = counters.get('by_market_no_line', {})
                print(f"\n   📈 Lignes manquantes par marché:")
                for market, count in no_line_by_market.items():
                    print(f"      - {market}: {count}")

                low_edge_by_market = counters.get('by_market_low_edge', {})
                print(f"\n   ⚠️ Edge trop faible par marché:")
                for market, count in low_edge_by_market.items():
                    print(f"      - {market}: {count}")

                # Afficher quelques picks si disponibles
                if picks:
                    print(f"\n   🎲 Premiers picks:")
                    for pick in picks[:5]:
                        print(f"      - {pick.get('player_name')} ({pick.get('market')}) @ {pick.get('line')} - Edge: {pick.get('edge', 0):.1%}")
                else:
                    print(f"\n   ℹ️ Aucun pick sélectionné (peut être normal si edge/score trop faible)")

                break
            elif status == "error":
                print(f"\n❌ SCAN EN ERREUR: {results.get('error')}")
                break
            else:
                # En cours
                if i % 5 == 0:
                    print(f"   ... en cours ({i}s)")
        else:
            print(f"   ⚠️ Erreur HTTP {r.status_code}")

    except Exception as e:
        print(f"   ⚠️ Erreur: {e}")

print("\n✅ Test terminé!")

