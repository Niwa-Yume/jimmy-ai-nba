#!/usr/bin/env python3
"""
Test manuel de toutes les clés API The Odds
Affiche le statut de chaque clé (valide, quota dépassé, invalide)
"""

import os
import requests
from dotenv import load_dotenv

load_dotenv('../.env')

keys_str = os.getenv('THE_ODDS_API_KEY', '')
api_keys = [k.strip() for k in keys_str.split(',') if k.strip()]

print("\n" + "="*70)
print("🔑 TEST DES CLÉS API THE ODDS")
print("="*70 + "\n")

print(f"📊 {len(api_keys)} clé(s) trouvée(s) dans .env\n")

# URL de test simple (liste des sports)
test_url = "https://api.the-odds-api.com/v4/sports"

for i, key in enumerate(api_keys, 1):
    masked = key[:6] + "***" + key[-4:]
    print(f"🔑 Clé {i}/{len(api_keys)}: {masked}")

    try:
        response = requests.get(test_url, params={"apiKey": key}, timeout=5)

        if response.status_code == 200:
            # Vérifier les headers pour le quota
            remaining = response.headers.get('x-requests-remaining', 'N/A')
            used = response.headers.get('x-requests-used', 'N/A')
            print(f"   ✅ VALIDE")
            print(f"   📊 Quota: {remaining} requêtes restantes ({used} utilisées)")
        elif response.status_code == 401:
            print(f"   ❌ INVALIDE (HTTP 401)")
            print(f"   💡 Cette clé est incorrecte ou révoquée")
        elif response.status_code == 429:
            print(f"   ⚠️  QUOTA DÉPASSÉ (HTTP 429)")
            print(f"   💡 Cette clé a atteint sa limite de requêtes")
        else:
            print(f"   ⚠️  ERREUR HTTP {response.status_code}")
            print(f"   💬 {response.text[:100]}")

    except requests.Timeout:
        print(f"   ⏱️  TIMEOUT (pas de réponse en 5s)")
    except Exception as e:
        print(f"   ❌ ERREUR: {e}")

    print()

print("="*70)
print("\n💡 RECOMMANDATIONS:\n")
print("   • Clés VALIDES: Utilisables immédiatement")
print("   • Clés INVALIDES (401): Vérifier sur the-odds-api.com")
print("   • Clés QUOTA DÉPASSÉ (429): Attendre le renouvellement")
print("\n" + "="*70 + "\n")

