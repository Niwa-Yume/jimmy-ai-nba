#!/bin/bash
set -e
echo "🚀 Setup Jimmy AI sur VPS"
echo "========================="
VPS="juju@192.168.1.134"
# 1. Copier le .env
echo "📦 1/6 - Copie du .env..."
scp .env $VPS:/home/juju/jimmy-ai-nba/.env
# 2. Reconstruire avec data-pipeline
echo "🏗️  2/6 - Rebuild du backend avec data-pipeline..."
ssh $VPS "cd jimmy-ai-nba && docker compose build backend"
# 3. Redémarrer les conteneurs
echo "🐳 3/6 - Redémarrage des conteneurs..."
ssh $VPS "cd jimmy-ai-nba && docker compose up -d"
# 4. Peupler les joueurs
echo "👥 4/6 - Peuplement des joueurs..."
ssh $VPS "cd jimmy-ai-nba && docker compose exec -T backend python /app/data-pipeline/populate_players.py"
# 5. Sync des matchs
echo "🏀 5/6 - Synchronisation des matchs..."
ssh $VPS "cd jimmy-ai-nba && docker compose exec -T backend python /app/data-pipeline/sync_weekly_games_v2.py"
# 6. Vérification
echo "✅ 6/6 - Vérification..."
ssh $VPS "cd jimmy-ai-nba && docker compose ps"
echo ""
echo "✅ SETUP TERMINÉ!"
echo "📱 Frontend : https://jimmyainba.duckdns.org"
echo "🔌 Backend  : https://jimmyainba.duckdns.org/health"
