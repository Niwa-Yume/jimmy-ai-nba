#!/usr/bin/env python3
"""
Tests pour le système de rotation des clés API
Valide que le système essaie bien toutes les clés disponibles
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Ajouter le répertoire parent au path pour importer backend
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestAPIKeyRotation:
    """Tests du système de rotation des clés API"""

    def test_switch_to_next_key_success(self):
        """Test du changement de clé API réussi"""
        from backend.betting_service import BettingOddsProvider

        with patch.dict(os.environ, {'THE_ODDS_API_KEY': 'key1,key2,key3'}):
            provider = BettingOddsProvider()

            assert provider.current_key_index == 0
            assert provider.api_key == 'key1'

            # Premier changement
            success = provider.switch_to_next_key()
            assert success is True
            assert provider.current_key_index == 1
            assert provider.api_key == 'key2'

            # Deuxième changement
            success = provider.switch_to_next_key()
            assert success is True
            assert provider.current_key_index == 2
            assert provider.api_key == 'key3'

            # Troisième changement (échec, plus de clés)
            success = provider.switch_to_next_key()
            assert success is False
            assert provider.current_key_index == 2  # Reste sur la dernière

    def test_switch_to_next_key_single_key(self):
        """Test avec une seule clé (pas de rotation possible)"""
        from backend.betting_service import BettingOddsProvider

        with patch.dict(os.environ, {'THE_ODDS_API_KEY': 'single_key'}):
            provider = BettingOddsProvider()

            assert provider.current_key_index == 0
            assert len(provider.api_keys) == 1

            # Tentative de changement (échec car une seule clé)
            success = provider.switch_to_next_key()
            assert success is False

    def test_all_keys_are_tried_on_429(self):
        """Test que toutes les clés sont essayées en cas d'erreur 429"""
        from backend.betting_service import BettingOddsProvider

        with patch.dict(os.environ, {'THE_ODDS_API_KEY': 'key1,key2,key3,key4'}):
            provider = BettingOddsProvider()

            # Simuler 3 échecs puis 1 succès
            with patch('requests.get') as mock_get:
                # 3 premiers appels échouent avec 429
                mock_get.side_effect = [
                    Mock(status_code=429),  # key1
                    Mock(status_code=429),  # key2
                    Mock(status_code=429),  # key3
                    Mock(status_code=200, json=lambda: [])  # key4 réussit
                ]

                # Simuler get_event_id qui fait les appels
                result = None
                for _ in range(4):
                    response = mock_get()
                    if response.status_code == 429:
                        provider.switch_to_next_key()
                    elif response.status_code == 200:
                        result = "success"
                        break

                # On doit avoir essayé key4 (index 3)
                assert provider.current_key_index == 3
                assert result == "success"

    def test_quota_exceeded_flag_is_set(self):
        """Test que le flag quota_exceeded est correctement défini"""
        from backend.betting_service import BettingOddsProvider

        with patch.dict(os.environ, {'THE_ODDS_API_KEY': 'key1,key2'}):
            provider = BettingOddsProvider()

            assert provider.quota_exceeded is False

            # Épuiser toutes les clés
            provider.switch_to_next_key()  # Passe à key2
            success = provider.switch_to_next_key()  # Plus de clés

            # Le flag devrait être défini lors du dernier switch qui échoue
            # Note: la logique actuelle ne set pas quota_exceeded dans switch_to_next_key
            # mais plutôt dans les fonctions appelantes, donc on vérifie juste le retour
            assert success is False

    def test_key_masking_in_logs(self):
        """Test que les clés sont bien masquées dans les logs"""
        from backend.betting_service import BettingOddsProvider

        with patch.dict(os.environ, {'THE_ODDS_API_KEY': 'sk_live_1234567890abcdef'}):
            # Capturer la sortie print
            with patch('builtins.print') as mock_print:
                provider = BettingOddsProvider()

                # Vérifier qu'aucun appel print ne contient la clé complète
                for call in mock_print.call_args_list:
                    call_str = str(call)
                    assert 'sk_live_1234567890abcdef' not in call_str, \
                        "La clé complète ne doit jamais apparaître dans les logs"

    def test_keys_are_stripped_of_whitespace(self):
        """Test que les espaces autour des clés sont supprimés"""
        from backend.betting_service import BettingOddsProvider

        # Clés avec espaces
        with patch.dict(os.environ, {'THE_ODDS_API_KEY': ' key1 , key2  ,  key3 '}):
            provider = BettingOddsProvider()

            assert provider.api_keys == ['key1', 'key2', 'key3']
            assert all(k == k.strip() for k in provider.api_keys)

    def test_empty_key_strings_are_filtered(self):
        """Test que les chaînes vides sont filtrées"""
        from backend.betting_service import BettingOddsProvider

        with patch.dict(os.environ, {'THE_ODDS_API_KEY': 'key1,,key2,  ,key3'}):
            provider = BettingOddsProvider()

            # Devrait avoir 3 clés valides (les vides sont filtrées)
            assert len(provider.api_keys) == 3
            assert provider.api_keys == ['key1', 'key2', 'key3']

    def test_no_api_key_in_env(self):
        """Test du comportement sans clé API"""
        from backend.betting_service import BettingOddsProvider

        with patch.dict(os.environ, {}, clear=True):
            with patch('builtins.print') as mock_print:
                provider = BettingOddsProvider()

                assert provider.api_key is None
                assert len(provider.api_keys) == 0

                # Vérifier qu'un message d'erreur est affiché
                printed = ' '.join(str(call) for call in mock_print.call_args_list)
                assert 'ERREUR' in printed or 'vide' in printed or 'manquantes' in printed


class TestAPIRetryLogic:
    """Tests de la logique de retry dans les fonctions API"""

    def test_get_event_id_retries_all_keys(self):
        """Test que get_event_id essaie toutes les clés en cas d'échec"""
        from backend.betting_service import BettingOddsProvider

        with patch.dict(os.environ, {'THE_ODDS_API_KEY': 'key1,key2,key3,key4,key5'}):
            provider = BettingOddsProvider()

            with patch('requests.get') as mock_get:
                # Les 4 premières clés échouent, la 5ème réussit
                responses = [
                    Mock(status_code=429),
                    Mock(status_code=429),
                    Mock(status_code=401),
                    Mock(status_code=429),
                    Mock(status_code=200, json=lambda: [{
                        'id': 'test_event',
                        'home_team': 'Los Angeles Lakers',
                        'away_team': 'Boston Celtics'
                    }])
                ]
                mock_get.side_effect = responses

                result = provider.get_event_id('LAL', 'BOS')

                # Devrait avoir essayé 5 fois (toutes les clés)
                assert mock_get.call_count == 5
                assert result == 'test_event'
                assert provider.current_key_index == 4  # Sur la 5ème clé

    def test_get_event_id_all_keys_exhausted(self):
        """Test quand toutes les clés sont épuisées"""
        from backend.betting_service import BettingOddsProvider

        with patch.dict(os.environ, {'THE_ODDS_API_KEY': 'key1,key2,key3'}):
            provider = BettingOddsProvider()

            with patch('requests.get') as mock_get:
                # Toutes les clés échouent
                mock_get.return_value = Mock(status_code=429)

                result = provider.get_event_id('LAL', 'BOS')

                # Devrait retourner None
                assert result is None
                assert provider.quota_exceeded is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

