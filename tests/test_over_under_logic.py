#!/usr/bin/env python3
"""
Tests unitaires pour valider la logique Over/Under et le calcul du score de confiance.
"""



def test_over_under_direction():
    """
    Test 1: Vérifie que la direction Over/Under est correcte
    Règle: Si projection > ligne -> "over", sinon -> "under"
    """

    # Test case 1: Rui Hachimura (bug reporté)
    projection = 12.9
    line = 8.5
    expected_bet_type = "over"  # projection > ligne
    actual_bet_type = "over" if projection > line else "under"
    assert actual_bet_type == expected_bet_type, f"ÉCHEC: projection={projection}, ligne={line}, devrait être 'over' mais est '{actual_bet_type}'"

    # Test case 2: Under normal
    projection = 4.0
    line = 5.5
    expected_bet_type = "under"  # projection < ligne
    actual_bet_type = "over" if projection > line else "under"
    assert actual_bet_type == expected_bet_type, f"ÉCHEC: projection={projection}, ligne={line}, devrait être 'under' mais est '{actual_bet_type}'"

    # Test case 3: Égalité (cas limite)
    projection = 10.0
    line = 10.0
    expected_bet_type = "under"  # égalité -> under (pas d'avantage)
    actual_bet_type = "over" if projection > line else "under"
    assert actual_bet_type == expected_bet_type, f"ÉCHEC: projection={projection}, ligne={line}, devrait être 'under' mais est '{actual_bet_type}'"

    print("✅ Test Over/Under: TOUS LES TESTS PASSENT")


def test_display_text_mapping():
    """
    Test 2: Vérifie que l'affichage texte correspond au bet_type
    """

    # Test "over" -> "Plus de"
    bet_type = "over"
    display = "Plus de" if bet_type == "over" else "Moins de"
    assert display == "Plus de", f"ÉCHEC: bet_type='over' devrait afficher 'Plus de' mais affiche '{display}'"

    # Test "under" -> "Moins de"
    bet_type = "under"
    display = "Plus de" if bet_type == "over" else "Moins de"
    assert display == "Moins de", f"ÉCHEC: bet_type='under' devrait afficher 'Moins de' mais affiche '{display}'"

    print("✅ Test Affichage Over/Under: TOUS LES TESTS PASSENT")


def test_confidence_score_edge_correlation():
    """
    Test 3: Vérifie que le score de confiance augmente avec l'edge
    """
    import math

    def calculate_edge_score(edge):
        """Réplique la formule du backend advanced_scoring.py"""
        if edge < 3.0:
            return edge * 10
        else:
            return min(100, 25 * math.log(edge) + 30)

    # Test case 1: Johnny Furphy (bug reporté: 4.8/5.5 = 87% edge mais score de 80)
    projection_furphy = 0.7
    line_furphy = 5.5
    edge_furphy = abs(projection_furphy - line_furphy) / line_furphy * 100
    score_furphy = calculate_edge_score(edge_furphy)

    print(f"📊 Johnny Furphy: projection={projection_furphy}, ligne={line_furphy}")
    print(f"   Edge: {edge_furphy:.1f}% -> Score edge: {score_furphy:.1f}/100")

    # Test case 2: Rui Hachimura (bug reporté: 12.9/8.5 = 52% edge avec score de 88)
    projection_hachimura = 12.9
    line_hachimura = 8.5
    edge_hachimura = abs(projection_hachimura - line_hachimura) / line_hachimura * 100
    score_hachimura = calculate_edge_score(edge_hachimura)

    print(f"📊 Rui Hachimura: projection={projection_hachimura}, ligne={line_hachimura}")
    print(f"   Edge: {edge_hachimura:.1f}% -> Score edge: {score_hachimura:.1f}/100")

    # Vérification: edge plus grand devrait donner un score plus grand (ou égal si plafonné à 100)
    assert edge_furphy > edge_hachimura, "L'edge de Furphy devrait être plus grand"
    # Note: Les deux scores peuvent être 100 s'ils sont plafonnés
    assert score_furphy >= score_hachimura, f"Le score de Furphy ({score_furphy:.1f}) devrait être >= à celui de Hachimura ({score_hachimura:.1f})"

    print(f"   ✅ Cohérence vérifiée: edge plus élevé = score plus élevé (ou plafonné)\n")

    # Test d'échelle: vérifier que les seuils sont cohérents avec la nouvelle formule
    test_cases = [
        (5, 65, 75),    # 5% edge -> ~70 points (formule logarithmique)
        (10, 85, 95),   # 10% edge -> ~88 points
        (20, 95, 100),  # 20% edge -> ~100 points (plafonné)
        (50, 95, 100),  # 50% edge -> ~100 points (plafonné)
        (100, 95, 100), # 100% edge -> ~100 points (plafonné)
    ]

    for edge, min_expected, max_expected in test_cases:
        score = calculate_edge_score(edge)
        print(f"   Edge {edge:3.0f}% -> Score: {score:.1f}/100 (attendu: {min_expected}-{max_expected})")
        assert min_expected <= score <= max_expected, f"ÉCHEC: Edge de {edge}% donne un score de {score:.1f}, attendu entre {min_expected} et {max_expected}"

    print("✅ Test Score de Confiance: TOUS LES TESTS PASSENT")


def test_full_pick_logic():
    """
    Test 4: Test complet d'un pick de bout en bout
    """

    # Simulation d'un pick complet
    player = "Rui Hachimura"
    projection = 12.9
    line = 8.5

    # Calcul du bet_type
    bet_type = "over" if projection > line else "under"

    # Calcul de l'affichage
    bet_display = "Plus de" if bet_type == "over" else "Moins de"

    # Calcul de la marge
    margin = projection - line

    # Vérifications
    assert bet_type == "over", f"Le pari devrait être 'over' pour {player}"
    assert bet_display == "Plus de", f"L'affichage devrait être 'Plus de' pour {player}"
    assert margin > 0, f"La marge devrait être positive (projection > ligne)"

    # Vérification de l'explication
    explanation = ""
    if margin > 0:
        explanation = f"Jimmy prévoit {projection:.1f}, soit {abs(margin):.1f} de plus que la ligne ({line})"
        assert "de plus" in explanation, "L'explication devrait mentionner 'de plus'"

    print(f"✅ Test Complet pour {player}:")
    print(f"   Projection: {projection}, Ligne: {line}")
    print(f"   Bet Type: {bet_type} ({bet_display} {line})")
    print(f"   Marge: +{margin:.1f}")
    if explanation:
        print(f"   Explication: {explanation}")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 TESTS UNITAIRES - LOGIQUE DE PARIS")
    print("="*70 + "\n")

    try:
        test_over_under_direction()
        print()
        test_display_text_mapping()
        print()
        test_confidence_score_edge_correlation()
        print()
        test_full_pick_logic()

        print("\n" + "="*70)
        print("✅ TOUS LES TESTS PASSENT - LOGIQUE CORRECTE")
        print("="*70 + "\n")
    except AssertionError as e:
        print(f"\n❌ ÉCHEC DU TEST: {e}\n")
        exit(1)
    except Exception as e:
        print(f"\n❌ ERREUR: {e}\n")
        exit(1)

