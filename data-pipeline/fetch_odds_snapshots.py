"""Fetch des cotes The-Odds-API et écriture dans odds_snapshots avec traçabilité ingestion_runs."""
import os
import sys
from pathlib import Path
import json

# Ensure project root on PYTHONPATH so `backend` imports work when called from data-pipeline
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from datetime import datetime, timedelta
from typing import Optional
from backend.betting_service import BettingOddsProvider
from backend.database import SessionLocal
from backend import models


def create_ingestion_run(db, source: str, scope: Optional[str] = None, version_tag: Optional[str] = None) -> int:
    run = models.IngestionRun(
        source=source,
        scope=scope,
        version_tag=version_tag,
        status="running",
        started_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run.id


def finish_ingestion_run(db, run_id: int, status: str = "success", meta: Optional[dict] = None):
    db.query(models.IngestionRun).filter(models.IngestionRun.id == run_id).update({
        models.IngestionRun.status: status,
        models.IngestionRun.ended_at: datetime.utcnow(),
        models.IngestionRun.meta: json.dumps(meta or {}),
        models.IngestionRun.updated_at: datetime.utcnow(),
    })
    db.commit()


def fetch_odds_for_upcoming_games(days_ahead: int = 2, ttl_hours: int = 4, version_tag: Optional[str] = None):
    provider = BettingOddsProvider()
    if provider.quota_exceeded or not provider.api_key:
        print("❌ Pas de clé The-Odds-API disponible.")
        return

    with SessionLocal() as db:
        run_id = create_ingestion_run(db, source="the-odds-api", scope=f"games_next_{days_ahead}d", version_tag=version_tag)
        try:
            today = datetime.utcnow().date()
            until = today + timedelta(days=days_ahead)
            games = db.query(models.GameSchedule).filter(
                models.GameSchedule.game_date >= today,
                models.GameSchedule.game_date <= until
            ).all()

            success = 0
            skipped = 0
            for g in games:
                ok = provider.fetch_odds_snapshots_for_game(
                    db,
                    game_id=g.nba_game_id,
                    home_code=g.home_team_code,
                    away_code=g.away_team_code,
                    ingestion_run_id=run_id,
                    ttl_hours=ttl_hours,
                )
                if ok:
                    success += 1
                else:
                    skipped += 1

            finish_ingestion_run(db, run_id, status="success", meta={"success": success, "skipped": skipped, "games": len(games)})
            print(f"📥 Odds fetch terminé. Success: {success}, Skipped: {skipped}, Games: {len(games)}")
        except Exception as e:
            db.rollback()
            finish_ingestion_run(db, run_id, status="failed", meta={"error": str(e)})
            print(f"❌ Erreur fetch_odds_for_upcoming_games: {e}")


if __name__ == "__main__":
    days = int(os.getenv("ODDS_DAYS_AHEAD", "2"))
    ttl = int(os.getenv("ODDS_TTL_HOURS", "4"))
    tag = os.getenv("ODDS_VERSION_TAG")
    fetch_odds_for_upcoming_games(days_ahead=days, ttl_hours=ttl, version_tag=tag)
