#!/usr/bin/env python3
"""
Script pour debug : afficher les valeurs d'edge calculées lors d'un scan
"""
import requests
import time

print("🔍 DEBUG: Valeurs d'edge calculées\n")

# Lancer un scan
print("1️⃣ Lancement d'un scan...")
r = requests.post("http://localhost:8000/analysis/start-scan", timeout=10)
scan_id = r.json().get("job_id")
print(f"   Scan ID: {scan_id}\n")

# Attendre la fin
print("2️⃣ Attente des résultats...")
for i in range(60):
    time.sleep(1)
    r = requests.get(f"http://localhost:8000/analysis/scan-results/{scan_id}", timeout=5)
    results = r.json()

    if results.get("status") == "completed":
        counters = results.get("debug_counters", {})
        picks = results.get("picks", [])

        print(f"\n✅ SCAN TERMINÉ")
        print(f"   Total vérifié: {counters.get('total_checked', 0)}")
        print(f"   Rejetés (low_edge): {counters.get('low_edge', 0)}")
        print(f"   Inclus: {counters.get('included', 0)}")
        print(f"   Picks retournés: {len(picks)}")

        if picks:
            print(f"\n📊 Exemples de picks ACCEPTÉS:")
            for pick in picks[:5]:
                edge = pick.get('edge', 0)
                print(f"   - {pick['player_name']} {pick['market']}: Edge = {edge:.2f}%")

        # Afficher les compteurs par marché
        by_market = counters.get('by_market_low_edge', {})
        print(f"\n❌ Rejetés par marché (low_edge):")
        for market, count in by_market.items():
            print(f"   - {market}: {count}")

        break
    elif i % 5 == 0:
        print(f"   ... {i}s")

print("\n✅ Debug terminé!")

