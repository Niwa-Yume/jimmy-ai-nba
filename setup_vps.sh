#!/bin/bash
set -e

echo "🚀 Setup Jimmy AI sur VPS"
echo "========================="

VPS="juju@192.168.1.134"

# 1. Copier le .env
echo "📦 1/5 - Copie du .env..."
scp .env $VPS:/home/juju/jimmy-ai-nba/.env

# 2. S'assurer que docker compose est up
echo "🐳 2/5 - Démarrage des conteneurs..."
ssh $VPS "cd jimmy-ai-nba && docker compose up -d"

# 3. Peupler les joueurs
echo "👥 3/5 - Peuplement des joueurs..."
ssh $VPS "cd jimmy-ai-nba && docker compose exec -T backend python /app/../data-pipeline/populate_players.py"

# 4. Sync des matchs
echo "🏀 4/5 - Synchronisation des matchs..."
ssh $VPS "cd jimmy-ai-nba && docker compose exec -T backend python /app/../data-pipeline/sync_weekly_games_v2.py"

# 5. Vérification
echo "✅ 5/5 - Vérification..."
ssh $VPS "cd jimmy-ai-nba && docker compose ps"
ssh $VPS "curl -s http://localhost:8000/health"
ssh $VPS "curl -s http://localhost:8501" | head -20

echo ""
echo "✅ SETUP TERMINÉ !"
echo "📍 Frontend: http://192.168.1.134:8501"
echo "📍 Backend: http://192.168.1.134:8000"

