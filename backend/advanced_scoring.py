"""
Module de scoring avancé pour filtrer les meilleurs picks de paris sportifs NBA.
Prend en compte : forme récente, matchup, minutes, blessures, volatilité, edge.
"""
from typing import Dict, Optional, Tuple
from sqlalchemy.orm import Session
from backend import models
from datetime import datetime, timedelta


class AdvancedScorer:
    """
    Calcule un score de confiance avancé basé sur plusieurs critères :
    - Forme récente (derniers matchs)
    - Matchup défensif (rating de l'équipe adverse)
    - Volatilité des stats (écart-type)
    - Minutes jouées récemment
    - Edge (écart % entre projection et ligne)
    - Statut blessure et probabilité de jouer
    """

    # Seuils de filtrage équilibrés pour picks de qualité
    MIN_SCORE = 45  # Score minimum requis (45/100) - Baissé pour avoir plus de picks
    MIN_EDGE = 0.1  # Edge minimum en % (0.1% min) - Quasi désactivé, on se base sur le score
    MIN_SAMPLE_SIZE = 5  # Nombre min de matchs pour projection fiable (5 matchs minimum)
    MAX_PICKS = 50  # Maximum de picks à retourner

    # Poids des différents facteurs dans le score
    WEIGHTS = {
        'recent_form': 0.25,      # Forme récente (25%)
        'matchup': 0.20,          # Qualité du matchup (20%)
        'consistency': 0.20,      # Consistance/Volatilité (20%)
        'minutes': 0.15,          # Minutes jouées (15%)
        'edge': 0.20              # Edge vs ligne (20%)
    }

    def __init__(self, db: Session):
        self.db = db

    def calculate_advanced_score(
        self,
        player_id: int,
        projection_data: Dict,
        line: float,
        opponent_team_code: str,
        stat_type: str,
        injury_status: Optional[str] = None,
        play_probability: Optional[float] = None
    ) -> Tuple[float, str, Dict]:
        """
        Calcule le score avancé pour un pick.

        Returns:
            (score, tag, details) où details contient le détail des sous-scores
        """

        if not projection_data or 'projections' not in projection_data:
            return 0.0, "NO_DATA", {}

        stat_data = projection_data['projections'].get(stat_type, {})
        if not stat_data:
            return 0.0, "NO_STAT", {}

        projection = stat_data.get('projection', 0)
        if projection <= 0 or line <= 0:
            return 0.0, "INVALID", {}

        # 1. EDGE : écart entre projection et ligne
        edge = abs(projection - line) / line * 100

        # ⚠️ BUGFIX CRITIQUE : Ne pas filtrer ici ! Le filtrage se fait dans should_include_pick()
        # On calcule le score complet d'abord, puis on filtre à la fin
        edge_score = min(100, edge * 10)  # 5% edge = 50pts, 10% edge = 100pts

        # 2. FORME RÉCENTE : performance des 5 derniers matchs
        recent_form_score = self._calculate_recent_form(
            player_id, stat_type, projection
        )

        # 3. MATCHUP : qualité défensive de l'adversaire
        matchup_score = self._calculate_matchup_quality(
            opponent_team_code, stat_type
        )

        # 4. CONSISTANCE : volatilité des stats
        consistency_score = self._calculate_consistency(
            player_id, stat_type, stat_data
        )

        # 5. MINUTES : stabilité des minutes récentes
        minutes_score = self._calculate_minutes_stability(player_id)

        # Score de base (avant pénalités)
        base_score = (
            edge_score * self.WEIGHTS['edge'] +
            recent_form_score * self.WEIGHTS['recent_form'] +
            matchup_score * self.WEIGHTS['matchup'] +
            consistency_score * self.WEIGHTS['consistency'] +
            minutes_score * self.WEIGHTS['minutes']
        )

        # 6. PÉNALITÉS : blessures, probabilité de jeu
        penalty_factor = self._calculate_injury_penalty(
            injury_status, play_probability
        )

        final_score = base_score * penalty_factor

        # Tag basé sur le score final
        if final_score >= 85:
            tag = "🔥 EXCELLENT"
        elif final_score >= 75:
            tag = "⭐ TRÈS BON"
        elif final_score >= 65:
            tag = "✅ BON"
        elif final_score >= 60:
            tag = "⚠️ CORRECT"
        else:
            tag = "❌ FAIBLE"

        details = {
            'base_score': round(base_score, 1),
            'final_score': round(final_score, 1),
            'edge': round(edge, 1),
            'edge_score': round(edge_score, 1),
            'recent_form_score': round(recent_form_score, 1),
            'matchup_score': round(matchup_score, 1),
            'consistency_score': round(consistency_score, 1),
            'minutes_score': round(minutes_score, 1),
            'penalty_factor': round(penalty_factor, 2),
            'tag': tag
        }

        return final_score, tag, details

    def _calculate_recent_form(
        self, player_id: int, stat_type: str, projection: float
    ) -> float:
        """Score basé sur les 5 derniers matchs vs projection."""
        try:
            # Récupérer les 5 derniers matchs
            recent_games = self.db.query(models.PlayerGameStats).filter(
                models.PlayerGameStats.player_id == player_id
            ).order_by(
                models.PlayerGameStats.id.desc()
            ).limit(5).all()

            if len(recent_games) < 3:
                return 50.0  # Score neutre si pas assez de données

            stat_mapping = {
                'points': 'points',
                'rebounds': 'rebounds',
                'assists': 'assists',
                'blocks': 'blocks',
                'steals': 'steals'
            }

            stat_field = stat_mapping.get(stat_type)
            if not stat_field:
                return 50.0

            values = [getattr(g, stat_field, 0) or 0 for g in recent_games]
            recent_avg = sum(values) / len(values)

            # Si forme récente > projection, c'est bon signe
            if recent_avg >= projection * 1.1:
                return 90.0
            elif recent_avg >= projection:
                return 75.0
            elif recent_avg >= projection * 0.9:
                return 60.0
            else:
                return 40.0

        except Exception:
            return 50.0

    def _calculate_matchup_quality(
        self, opponent_team_code: str, stat_type: str
    ) -> float:
        """Score basé sur la défense adverse (facile vs difficile)."""
        # TODO : implémenter avec defense_ratings si disponible
        # Pour l'instant, retourner score neutre
        return 70.0

    def _calculate_consistency(
        self, player_id: int, stat_type: str, stat_data: Dict
    ) -> float:
        """Score basé sur la volatilité (écart-type bas = consistant = bon)."""
        try:
            std_dev = stat_data.get('std_dev', 0)
            avg = stat_data.get('projection', 0)

            if avg <= 0:
                return 50.0

            # Coefficient de variation
            cv = (std_dev / avg) * 100

            # CV bas = très consistant
            if cv < 20:
                return 90.0
            elif cv < 30:
                return 75.0
            elif cv < 40:
                return 60.0
            else:
                return 40.0

        except Exception:
            return 50.0

    def _calculate_minutes_stability(self, player_id: int) -> float:
        """Score basé sur la stabilité des minutes jouées récemment."""
        try:
            recent_games = self.db.query(models.PlayerGameStats).filter(
                models.PlayerGameStats.player_id == player_id
            ).order_by(
                models.PlayerGameStats.id.desc()
            ).limit(5).all()

            if len(recent_games) < 3:
                return 50.0

            minutes = [g.minutes_played or 0 for g in recent_games]
            avg_minutes = sum(minutes) / len(minutes)

            # Titulaires avec minutes stables
            if avg_minutes >= 30:
                return 90.0
            elif avg_minutes >= 25:
                return 75.0
            elif avg_minutes >= 20:
                return 60.0
            else:
                return 40.0

        except Exception:
            return 50.0

    def _calculate_injury_penalty(
        self, injury_status: Optional[str], play_probability: Optional[float]
    ) -> float:
        """Facteur de pénalité (0.0 à 1.0) basé sur le statut blessure."""
        # Pénalités équilibrées et réalistes
        status_penalties = {
            'OUT': 0.0,
            'DOUBTFUL': 0.5,      # Pénalisé mais pas trop
            'QUESTIONABLE': 0.85,  # Très légère pénalité
            'DAY_TO_DAY': 0.95,   # Presque aucune pénalité (très courant en NBA)
            'GTD': 0.85,          # Légère pénalité
            'PROBABLE': 0.95,     # Presque pas pénalisé
            'HEALTHY': 1.0
        }

        status_factor = status_penalties.get(
            str(injury_status or 'HEALTHY').upper(), 1.0
        )

        # Si probabilité de jouer disponible, appliquer pénalité équilibrée
        prob_factor = 1.0
        if play_probability is not None:
            prob = float(play_probability) / 100.0
            # Pénalité si proba < 70%
            if prob < 0.7:
                prob_factor = prob * 0.8
            else:
                prob_factor = max(0.85, prob)

        return min(status_factor, prob_factor)

    def should_include_pick(
        self,
        score: float,
        edge: float,
        sample_size: int,
        injury_status: Optional[str] = None
    ) -> bool:
        """
        Détermine si un pick doit être inclus dans les résultats finaux.
        Critères équilibrés pour qualité sans trop filtrer.
        """
        # Éliminer uniquement les OUT (DOUBTFUL peut passer si bon score)
        if injury_status and str(injury_status).upper() == 'OUT':
            return False

        # Score minimum requis (50/100)
        if score < self.MIN_SCORE:
            return False

        # Edge minimum requis (3.5%)
        if edge < self.MIN_EDGE:
            return False

        # Échantillon minimum requis (8 matchs)
        if sample_size < self.MIN_SAMPLE_SIZE:
            return False

        return True

