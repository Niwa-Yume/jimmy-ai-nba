#!/bin/bash
# Script pour appliquer les migrations manquantes sur le VPS
set -e

VPS="juju@192.168.1.134"

echo "🔧 Application des migrations sur le VPS..."
echo "============================================="

# 1. Copier la migration sur le VPS
echo "📦 1/3 - Copie de la migration..."
scp database/migrations/005_fix_player_stats_constraint.sql $VPS:/tmp/

# 2. Appliquer la migration
echo "🗄️  2/3 - Application de la migration..."
ssh $VPS << 'ENDSSH'
cd jimmy-ai-nba
docker compose exec -T db psql -U jimmy_user -d jimmy_nba_db < /tmp/005_fix_player_stats_constraint.sql
ENDSSH

# 3. Vérifier
echo "✅ 3/3 - Vérification..."
ssh $VPS << 'ENDSSH'
cd jimmy-ai-nba
docker compose exec -T db psql -U jimmy_user -d jimmy_nba_db -c "
SELECT conname, contype
FROM pg_constraint
WHERE conrelid = 'player_game_stats'::regclass;
"
ENDSSH

echo ""
echo "✅ Migration terminée !"

