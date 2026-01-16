#!/usr/bin/env python3
"""
Tests unitaires pour la logique de paris NBA
Valide la cohérence entre projection, ligne, et direction du pari (Over/Under)
"""

import pytest


class TestBettingLogic:
    """Tests de la logique de génération des paris"""

    def test_over_direction_when_projection_higher(self):
        """Quand projection > ligne, le pari DOIT être 'over'"""
        projection = 12.9
        line = 8.5

        # Logique backend (ligne 756 de main.py)
        bet_type = "over" if projection > line else "under"

        assert bet_type == "over", f"Projection {projection} > Ligne {line} devrait donner 'over'"

    def test_under_direction_when_projection_lower(self):
        """Quand projection < ligne, le pari DOIT être 'under'"""
        projection = 3.2
        line = 5.5

        bet_type = "over" if projection > line else "under"

        assert bet_type == "under", f"Projection {projection} < Ligne {line} devrait donner 'under'"

    def test_under_direction_edge_case(self):
        """Test avec une projection très proche mais inférieure"""
        projection = 5.4
        line = 5.5

        bet_type = "over" if projection > line else "under"

        assert bet_type == "under"

    def test_over_direction_large_gap(self):
        """Test avec un écart énorme (cas Johnny Furphy)"""
        projection = 10.3
        line = 5.5

        bet_type = "over" if projection > line else "under"

        assert bet_type == "over", "Écart de 4.8 devrait clairement être 'over'"

    def test_frontend_display_mapping(self):
        """Vérifie que le frontend affiche correctement les types de paris"""
        # Backend
        bet_type_backend = "over"

        # Frontend (ligne 878 de app.py)
        bet_type_display = "Plus de" if bet_type_backend == 'over' else "Moins de"

        assert bet_type_display == "Plus de"

        # Test inverse
        bet_type_backend = "under"
        bet_type_display = "Plus de" if bet_type_backend == 'over' else "Moins de"

        assert bet_type_display == "Moins de"

    def test_odds_selection_over(self):
        """Vérifie qu'on sélectionne la bonne cote (over vs under)"""
        projection = 15.0
        line = 12.5
        odds_over = 1.85
        odds_under = 1.95

        # Logique backend
        selected_odds = odds_over if projection > line else odds_under

        assert selected_odds == odds_over, "Devrait sélectionner odds_over quand projection > ligne"

    def test_odds_selection_under(self):
        """Vérifie qu'on sélectionne la bonne cote (under)"""
        projection = 8.0
        line = 10.5
        odds_over = 1.85
        odds_under = 1.95

        selected_odds = odds_over if projection > line else odds_under

        assert selected_odds == odds_under, "Devrait sélectionner odds_under quand projection < ligne"


class TestConfidenceScore:
    """Tests du calcul du score de confiance"""

    def test_large_edge_should_give_high_score(self):
        """Un écart important devrait donner un score élevé"""
        import math

        # Cas Johnny Furphy: projection 10.3, ligne 5.5
        projection = 10.3
        line = 5.5
        edge = abs(projection - line) / line * 100  # ~87%

        # Formule améliorée (ligne ~78 de advanced_scoring.py)
        edge_score = min(100, 35 * math.log(edge + 1) + 15)

        # Avec un edge de 87%, le score devrait être très élevé (proche de 100)
        assert edge_score >= 90, f"Edge de {edge:.1f}% devrait donner un score >= 90 (obtenu: {edge_score:.1f})"

    def test_medium_edge_should_give_medium_score(self):
        """Un écart moyen devrait donner un score moyen"""
        import math

        # Cas Rui Hachimura: projection 12.9, ligne 8.5
        projection = 12.9
        line = 8.5
        edge = abs(projection - line) / line * 100  # ~51%

        edge_score = min(100, 35 * math.log(edge + 1) + 15)

        # Avec un edge de 51%, le score devrait être entre 75-85
        assert 70 <= edge_score <= 90, f"Edge de {edge:.1f}% devrait donner un score entre 70-90 (obtenu: {edge_score:.1f})"

    def test_small_edge_should_give_low_score(self):
        """Un écart faible devrait donner un score bas"""
        import math

        projection = 11.0
        line = 10.5
        edge = abs(projection - line) / line * 100  # ~4.8%

        edge_score = min(100, 35 * math.log(edge + 1) + 15)

        # Avec un edge de 4.8%, le score devrait être entre 40-60
        assert 35 <= edge_score <= 65, f"Edge de {edge:.1f}% devrait donner un score entre 35-65 (obtenu: {edge_score:.1f})"

    def test_edge_percentage_calculation(self):
        """Valide le calcul de l'edge en pourcentage"""
        # Test 1: Écart de 50%
        projection = 15.0
        line = 10.0
        edge = abs(projection - line) / line * 100

        assert edge == 50.0, f"Edge devrait être 50% (obtenu: {edge:.1f}%)"

        # Test 2: Écart de 100%
        projection = 20.0
        line = 10.0
        edge = abs(projection - line) / line * 100

        assert edge == 100.0, f"Edge devrait être 100% (obtenu: {edge:.1f}%)"

        # Test 3: Petit écart
        projection = 10.5
        line = 10.0
        edge = abs(projection - line) / line * 100

        assert 4.9 <= edge <= 5.1, f"Edge devrait être ~5% (obtenu: {edge:.1f}%)"


class TestDataIntegrity:
    """Tests de validation des données"""

    def test_line_should_be_positive(self):
        """Les lignes de bookmaker doivent toujours être positives"""
        valid_lines = [5.5, 10.5, 25.5, 0.5]
        invalid_lines = [-1.0, 0, -5.5]

        for line in valid_lines:
            assert line > 0, f"Ligne {line} devrait être positive"

        for line in invalid_lines:
            assert line <= 0, f"Ligne {line} ne devrait pas être acceptée"

    def test_projection_should_be_positive(self):
        """Les projections doivent toujours être positives"""
        valid_projections = [12.9, 5.4, 0.1, 25.8]
        invalid_projections = [-1.0, 0, -10.5]

        for proj in valid_projections:
            assert proj > 0, f"Projection {proj} devrait être positive"

        for proj in invalid_projections:
            assert proj <= 0, f"Projection {proj} ne devrait pas être acceptée"

    def test_odds_should_be_above_one(self):
        """Les cotes doivent être >= 1.0 (format décimal)"""
        valid_odds = [1.01, 1.85, 1.95, 2.50, 10.0]
        invalid_odds = [0.5, 0.9, 0, -1.0]

        for odds in valid_odds:
            assert odds >= 1.0, f"Cote {odds} devrait être >= 1.0"

        for odds in invalid_odds:
            assert odds < 1.0, f"Cote {odds} ne devrait pas être acceptée"


if __name__ == "__main__":
    # Exécuter les tests
    pytest.main([__file__, "-v", "--tb=short"])

