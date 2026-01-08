#!/bin/bash
# Script de déploiement des corrections pour fix 0 picks

echo "🚀 Déploiement du fix pour 0 picks sur VPS..."
echo ""

VPS_HOST="juju@192.168.1.134"
PROJECT_DIR="/home/juju/jimmy-ai-nba"

echo "📤 Copie du fichier advanced_scoring.py vers le VPS..."
scp backend/advanced_scoring.py ${VPS_HOST}:${PROJECT_DIR}/backend/advanced_scoring.py

if [ $? -ne 0 ]; then
    echo "❌ Erreur lors de la copie du fichier"
    exit 1
fi

echo ""
echo "🔄 Redémarrage des services sur le VPS..."
ssh ${VPS_HOST} << 'ENDSSH'
cd /home/juju/jimmy-ai-nba

# Afficher les changements
echo "📊 Vérification des nouveaux seuils:"
grep "MIN_EDGE\|MIN_SCORE\|MIN_SAMPLE_SIZE" backend/advanced_scoring.py | head -3

# Redémarrer les containers Docker
echo ""
echo "🔄 Redémarrage des containers..."
docker compose down
docker compose up -d --build

# Attendre que les services démarrent
echo "⏳ Attente du démarrage des services (10s)..."
sleep 10

# Vérifier que les containers sont up
echo ""
echo "✅ État des containers:"
docker compose ps

ENDSSH

echo ""
echo "✅ Déploiement terminé!"
echo ""
echo "📋 Résumé des changements:"
echo "   - MIN_EDGE: 6.0% → 3.5%"
echo "   - MIN_SCORE: 55 → 50"
echo "   - MIN_SAMPLE_SIZE: 10 → 8"
echo "   - Pénalités blessures assouplies (DOUBTFUL, DAY_TO_DAY, GTD)"
echo ""
echo "🎯 Vous devriez maintenant avoir plus de picks disponibles!"

