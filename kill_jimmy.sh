#!/usr/bin/env bash
# Tue les instances de backend et frontend Jimmy.AI en cours d'exécution
set -euo pipefail

echo "🔪 Kill des processus Jimmy.AI (uvicorn / streamlit) ..."
pkill -f "uvicorn main:app" || true
pkill -f "uvicorn backend.main:app" || true
pkill -f "streamlit run" || true
pkill -f "python.*backend/main.py" || true
pkill -f "python.*frontend/app.py" || true

# Kill spécifique par port (plus robuste)
lsof -ti:8000 | xargs kill -9 2>/dev/null || true
lsof -ti:8501 | xargs kill -9 2>/dev/null || true

echo "✅ Terminé. Vérifiez avec : ps aux | egrep 'uvicorn|streamlit'"
