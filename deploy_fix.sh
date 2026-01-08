#!/bin/bash
set -e
VPS="juju@192.168.1.134"
echo "🚀 Déploiement des corrections sur VPS"
echo "========================================"
# 1. Pull les derniers changements sur le VPS
echo "📥 1/5 - Pull des changements..."
ssh $VPS "cd jimmy-ai-nba && git pull origin main"
# 2. Copier la migration
echo "📦 2/5 - Copie de la migration..."
scp database/migrations/005_fix_player_game_stats.sql $VPS:/home/juju/jimmy-ai-nba/database/migrations/
# 3. Rebuild du backend
echo "🏗️  3/5 - Rebuild du backend..."
ssh $VPS "cd jimmy-ai-nba && docker compose build --no-cache backend"
# 4. Redémarrer
echo "🔄 4/5 - Redémarrage..."
ssh $VPS "cd jimmy-ai-nba && docker compose down && docker compose up -d"
sleep 5
# 5. Appliquer la migration
echo "🔧 5/5 - Application de la migration..."
ssh $VPS "cd jimmy-ai-nba && docker compose exec -T db psql -U jimmy_user -d jimmy_nba_db < database/migrations/005_fix_player_game_stats.sql" || echo "⚠️  Migration déjà appliquée"
echo ""
echo "✅ Déploiement terminé!"
echo "🧪 Test du backend..."
ssh $VPS "curl -s http://localhost:8000/health"
