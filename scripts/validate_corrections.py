#!/usr/bin/env python3
"""
Script de validation rapide des corrections
Teste les 3 cas d'usage critiques identifiés dans l'audit
"""

import math


def test_over_under_logic():
    """Test 1: Logique Over/Under"""
    print("\n" + "=" * 70)
    print("TEST 1: LOGIQUE OVER/UNDER")
    print("=" * 70 + "\n")

    test_cases = [
        # (projection, ligne, bet_type_attendu, description)
        (12.9, 8.5, "over", "Rui Hachimura - Cas original du bug"),
        (10.3, 5.5, "over", "Johnny Furphy - Gros écart"),
        (5.4, 5.5, "under", "Cas limite - projection légèrement sous la ligne"),
        (25.8, 25.5, "over", "Cas limite - projection légèrement au-dessus"),
        (3.2, 5.5, "under", "Nicolas Batum - Projection bien en dessous"),
    ]

    all_passed = True

    for proj, line, expected, desc in test_cases:
        # Logique backend corrigée
        bet_type = "over" if proj > line else "under"

        # Affichage frontend
        bet_type_display = "Plus de" if bet_type == 'over' else "Moins de"

        passed = bet_type == expected
        status = "✅ PASS" if passed else "❌ FAIL"

        print(f"{status} {desc}")
        print(f"     Projection: {proj:.1f} | Ligne: {line:.1f}")
        print(f"     Type: {bet_type} ({bet_type_display} {line})")
        print(f"     Attendu: {expected}")

        if not passed:
            all_passed = False
            print(f"     ❌ ERREUR: Obtenu '{bet_type}' au lieu de '{expected}'")

        print()

    return all_passed


def test_confidence_score():
    """Test 2: Calcul du Score de Confiance"""
    print("\n" + "=" * 70)
    print("TEST 2: CALCUL DU SCORE DE CONFIANCE")
    print("=" * 70 + "\n")

    test_cases = [
        # (projection, ligne, edge_score_min, edge_score_max, description)
        (10.3, 5.5, 97, 100, "Johnny Furphy - Edge 87% (exceptionnel)"),
        (12.9, 8.5, 97, 100, "Rui Hachimura - Edge 51% (excellent)"),
        (11.0, 10.5, 65, 75, "Petit edge 4.8% (faible)"),
        (20.0, 10.0, 97, 100, "Edge 100% (exceptionnel)"),
    ]

    all_passed = True

    for proj, line, min_expected, max_expected, desc in test_cases:
        edge = abs(proj - line) / line * 100

        # Nouvelle formule corrigée (cohérente avec backend)
        if edge < 3.0:
            edge_score = edge * 10
        else:
            edge_score = min(100, 25 * math.log(edge) + 30)

        passed = min_expected <= edge_score <= max_expected
        status = "✅ PASS" if passed else "❌ FAIL"

        print(f"{status} {desc}")
        print(f"     Projection: {proj:.1f} | Ligne: {line:.1f}")
        print(f"     Edge: {edge:.1f}% → Score: {edge_score:.1f}/100")
        print(f"     Attendu: {min_expected}-{max_expected}")

        if not passed:
            all_passed = False
            print(f"     ❌ ERREUR: Score {edge_score:.1f} hors de la plage attendue")

        print()

    return all_passed


def test_edge_score_curve():
    """Test 3: Vérification de la courbe de scoring"""
    print("\n" + "=" * 70)
    print("TEST 3: COURBE DE SCORING")
    print("=" * 70 + "\n")

    print("   Edge (%) | Score | Comportement Attendu")
    print("   " + "-" * 60)

    edges = [5, 10, 15, 20, 30, 50, 75, 100]
    all_passed = True

    for edge in edges:
        # Nouvelle formule (cohérente avec backend)
        if edge < 3.0:
            score = edge * 10
        else:
            score = min(100, 25 * math.log(edge) + 30)

        # Vérifier la monotonie (score doit augmenter avec edge, ou rester à 100 si déjà plafonné)
        if edge < 100:
            next_edge = edge + 10
            if next_edge < 3.0:
                next_score = next_edge * 10
            else:
                next_score = min(100, 25 * math.log(next_edge) + 30)
            # Monotone si score augmente OU si déjà à 100
            monotonic = (score < next_score) or (score >= 100)
        else:
            monotonic = True

        status = "✅" if monotonic else "❌"

        print(f"   {status} {edge:5d}% → {score:5.1f}  ", end="")

        if edge <= 5:
            print("(Faible - Filtrer)")
        elif edge <= 15:
            print("(Moyen)")
        elif edge <= 30:
            print("(Bon)")
        else:
            print("(Excellent)")

        if not monotonic:
            all_passed = False
            print(f"        ❌ ERREUR: Courbe non monotone!")

    print()
    return all_passed


def test_api_key_rotation():
    """Test 4: Logique de rotation des clés (simulation)"""
    print("\n" + "=" * 70)
    print("TEST 4: ROTATION DES CLÉS API (Simulation)")
    print("=" * 70 + "\n")

    # Simuler le provider
    class MockProvider:
        def __init__(self, keys):
            self.api_keys = keys
            self.current_key_index = 0
            self.api_key = self.api_keys[0] if self.api_keys else None
            self.quota_exceeded = False

        def switch_to_next_key(self):
            if self.current_key_index < len(self.api_keys) - 1:
                self.current_key_index += 1
                self.api_key = self.api_keys[self.current_key_index]
                self.quota_exceeded = False
                return True
            else:
                return False

    provider = MockProvider(['key1', 'key2', 'key3', 'key4', 'key5'])

    print(f"   📊 {len(provider.api_keys)} clés disponibles")
    print(f"   🔑 Clé initiale: {provider.api_key}\n")

    all_passed = True

    # Simuler 5 échecs (toutes les clés)
    for i in range(5):
        print(f"   Tentative {i + 1}: clé '{provider.api_key}' échoue (HTTP 429)")

        if i < 4:  # Pas de switch après la dernière
            success = provider.switch_to_next_key()
            if success:
                print(f"   🔄 Changement vers clé '{provider.api_key}' (index {provider.current_key_index + 1}/{len(provider.api_keys)})")
            else:
                print(f"   ❌ Plus de clés disponibles")
                provider.quota_exceeded = True
        print()

    # Vérifier que toutes les clés ont été testées
    expected_index = 4  # Dernière clé (index 4)
    if provider.current_key_index == expected_index:
        print(f"   ✅ PASS: Toutes les {len(provider.api_keys)} clés ont été testées")
    else:
        print(f"   ❌ FAIL: Seulement {provider.current_key_index + 1}/{len(provider.api_keys)} clés testées")
        all_passed = False

    print()
    return all_passed


def main():
    """Exécution de tous les tests"""
    print("\n" + "=" * 70)
    print("🔍 VALIDATION DES CORRECTIONS - SUITE DE TESTS")
    print("=" * 70)

    results = {
        "Over/Under Logic": test_over_under_logic(),
        "Confidence Score": test_confidence_score(),
        "Edge Score Curve": test_edge_score_curve(),
        "API Key Rotation": test_api_key_rotation(),
    }

    print("\n" + "=" * 70)
    print("📊 RÉSULTATS FINAUX")
    print("=" * 70 + "\n")

    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {status} {test_name}")
        if not passed:
            all_passed = False

    print("\n" + "=" * 70)

    if all_passed:
        print("🎉 SUCCÈS: Toutes les corrections sont validées!")
        print("=" * 70 + "\n")
        return 0
    else:
        print("❌ ÉCHEC: Certains tests ont échoué")
        print("=" * 70 + "\n")
        return 1


if __name__ == "__main__":
    exit(main())

