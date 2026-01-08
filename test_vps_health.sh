#!/bin/bash
# Script de test post-déploiement

echo "🧪 Test du backend sur le VPS..."
echo ""

VPS_HOST="192.168.1.134"
BACKEND_URL="http://${VPS_HOST}:8000"

echo "1️⃣ Test de connexion au backend..."
response=$(curl -s -o /dev/null -w "%{http_code}" ${BACKEND_URL}/health)

if [ "$response" = "200" ]; then
    echo "   ✅ Backend accessible (HTTP 200)"
else
    echo "   ⚠️ Backend retourne : HTTP $response"
fi

echo ""
echo "2️⃣ Test de l'interface frontend..."
frontend_response=$(curl -s -o /dev/null -w "%{http_code}" http://${VPS_HOST}:8501)

if [ "$frontend_response" = "200" ]; then
    echo "   ✅ Frontend accessible (HTTP 200)"
else
    echo "   ⚠️ Frontend retourne : HTTP $frontend_response"
fi

echo ""
echo "3️⃣ Vérification des containers Docker..."
ssh juju@${VPS_HOST} "docker compose -f /home/juju/jimmy-ai-nba/docker-compose.yml ps --format 'table {{.Name}}\t{{.Status}}'"

echo ""
echo "4️⃣ Vérification des seuils dans le code déployé..."
ssh juju@${VPS_HOST} "grep 'MIN_EDGE\|MIN_SCORE\|MIN_SAMPLE_SIZE' /home/juju/jimmy-ai-nba/backend/advanced_scoring.py | grep '=' | head -3"

echo ""
echo "✅ Tests terminés!"
echo ""
echo "📱 Accédez à votre application :"
echo "   Frontend : http://${VPS_HOST}:8501"
echo "   Backend  : http://${VPS_HOST}:8000"

