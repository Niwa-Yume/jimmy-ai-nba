#!/bin/bash

# 🏀 Script de démarrage Jimmy.AI - script principal unique (remplace les versions v2/v3)
set -euo pipefail

# Trap pour cleanup
cleanup() {
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

echo "=============================================="
echo "🏀 Jimmy.AI - Démarrage"
echo "=============================================="

# Vérifier le répertoire
if [ ! -d "backend" ] || [ ! -d "frontend" ]; then
  echo "❌ Lance ce script depuis la racine du projet"
  exit 1
fi

# Activer l'environnement
if [ -f ".venv/bin/activate" ]; then
  echo "🔧 Activation de l'environnement virtuel..."
  source .venv/bin/activate
else
  echo "🔧 .venv introuvable. Création du virtualenv..."
  python3 -m venv .venv
  source .venv/bin/activate
fi

# Charger .env si présent (export simple pour uvicorn et processus)
if [ -f ".env" ]; then
  echo "📥 Chargement des variables d'environnement depuis .env"
  set -o allexport
  source .env
  set +o allexport
fi

# Installer les dépendances (tolérant)
echo "📦 Installation des dépendances backend..."
if [ -f backend/requirements.txt ]; then
  pip install --upgrade pip setuptools wheel >/tmp/jimmy-pip-backend.log 2>&1 || true
  pip install -r backend/requirements.txt >>/tmp/jimmy-pip-backend.log 2>&1 || echo "⚠️ Warning: certaines dépendances backend ont échoué (voir /tmp/jimmy-pip-backend.log)"
fi

if [ -f frontend/requirements.txt ]; then
  echo "📦 Installation des dépendances frontend..."
  pip install -r frontend/requirements.txt >>/tmp/jimmy-pip-frontend.log 2>&1 || echo "⚠️ Warning: certaines dépendances frontend ont échoué (voir /tmp/jimmy-pip-frontend.log)"
fi

# Nettoyage des anciens processus
echo "🧹 Nettoyage des processus existants..."
./kill_jimmy.sh >/dev/null 2>&1 || true
sleep 2

# Sync rapide des matchs (cache)
echo "📥 Synchronisation des matchs de la semaine (cache)..."
python3 data-pipeline/sync_weekly_games_v2.py >/tmp/jimmy-sync.log 2>&1 || true

# S'assurer que la DB a bien les colonnes nécessaires (migration légère)
echo "🛠️ Vérification / migration légère des tables (create_tables.py)..."
python3 database/create_tables.py >/tmp/jimmy-migrate.log 2>&1 || echo "⚠️ Migration échouée, voir /tmp/jimmy-migrate.log"

# Lancer backend (FastAPI) - lancer comme module depuis la racine
echo "🚀 Lancement du Backend (FastAPI)..."
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000 >/tmp/jimmy-backend.log 2>&1 &
BACKEND_PID=$!

# Attendre que le backend réponde (jusqu'à ~12s)
echo "⏳ Attente du backend..."
for i in {1..12}; do
  if curl -fsS --max-time 2 http://127.0.0.1:8000/health 2>/dev/null | grep -q "ok"; then
    BACKEND_OK=1
    break
  fi
  sleep 1
done

# Vérification backend
if [ "${BACKEND_OK:-0}" -eq 1 ] && [ -n "$BACKEND_PID" ]; then
  echo "✅ Backend OK (PID: $BACKEND_PID)"
else
  echo "❌ Backend ne répond pas"
  echo "📋 Logs backend : tail -n 200 /tmp/jimmy-backend.log"
  exit 1
fi

# Lancer frontend moderne (Streamlit)
echo "🎨 Lancement du Frontend (Streamlit)..."
streamlit run frontend/app.py --server.port 8501 >/tmp/jimmy-frontend.log 2>&1 &
FRONTEND_PID=$!

# Petit délai pour la vérification du frontend
sleep 2
if curl -fsS --max-time 2 http://127.0.0.1:8501/ 2>/dev/null; then
  echo "✅ Frontend OK (PID: $FRONTEND_PID)"
else
  echo "⚠️ Frontend peut ne pas être prêt immédiatement. Vérifiez /tmp/jimmy-frontend.log"
fi

echo ""
echo "=============================================="
echo "✅ Jimmy.AI opérationnel"
echo "📡 Backend  : http://127.0.0.1:8000"
echo "🎨 Frontend : http://localhost:8501"
echo "=============================================="
echo "🛑 Pour arrêter : ./kill_jimmy.sh"
echo "📋 Logs : tail -f /tmp/jimmy-backend.log /tmp/jimmy-frontend.log"

# Garder le script en vie tant que les services tournent
wait "$BACKEND_PID" "$FRONTEND_PID"
