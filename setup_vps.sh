#!/bin/bash
set -e
echo "🚀 Setup Jimmy AI sur VPS"
echo "========================="
VPS="juju@192.168.1.134"
# 1. Copier le .env
echo "📦 1/7 - Copie du .env..."
scp .env $VPS:/home/juju/jimmy-ai-nba/.env

# 2. Copier les migrations
echo "📦 2/7 - Copie des migrations..."
scp -r database/migrations $VPS:/home/juju/jimmy-ai-nba/database/

# 3. Reconstruire avec data-pipeline
echo "🏗️  3/7 - Rebuild du backend avec data-pipeline..."
ssh $VPS "cd jimmy-ai-nba && docker compose build backend"

# 4. Redémarrer les conteneurs
echo "🐳 4/7 - Redémarrage des conteneurs..."
ssh $VPS "cd jimmy-ai-nba && docker compose up -d"

# Attendre que la DB soit prête
echo "⏳ Attente de la DB..."
sleep 5

# 5. Appliquer les migrations
echo "🔧 5/7 - Application des migrations SQL..."
ssh $VPS "cd jimmy-ai-nba && docker compose exec -T db psql -U jimmy_user -d jimmy_nba_db < database/migrations/005_fix_player_game_stats.sql" || echo "⚠️  Migration déjà appliquée"

# 6. Peupler les joueurs
echo "👥 6/7 - Peuplement des joueurs..."
ssh $VPS "cd jimmy-ai-nba && docker compose exec -T backend python /app/data-pipeline/populate_players.py"

# 7. Sync des matchs
echo "🏀 7/7 - Synchronisation des matchs..."
ssh $VPS "cd jimmy-ai-nba && docker compose exec -T backend python /app/data-pipeline/sync_weekly_games_v2.py"

# Vérification
echo "✅ Vérification..."
ssh $VPS "cd jimmy-ai-nba && docker compose ps"
echo ""
echo "✅ SETUP TERMINÉ!"
echo "📱 Frontend : https://jimmyainba.duckdns.org"
echo "🔌 Backend  : https://jimmyainba.duckdns.org/health"
