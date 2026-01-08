#!/bin/bash
# Script de test rapide pour vérifier que le fix fonctionne

echo "🧪 Test rapide du fix 0 picks"
echo "=============================="
echo ""

VPS_IP="192.168.1.134"

echo "1️⃣ Vérification des seuils déployés..."
ssh juju@${VPS_IP} "grep 'MIN_EDGE =\|MIN_SCORE =\|MIN_SAMPLE_SIZE =' /home/juju/jimmy-ai-nba/backend/advanced_scoring.py" | head -3
echo ""

echo "2️⃣ État des containers Docker..."
ssh juju@${VPS_IP} "cd /home/juju/jimmy-ai-nba && docker compose ps --format 'table {{.Name}}\t{{.Status}}' 2>/dev/null || docker-compose ps --format 'table {{.Name}}\t{{.Status}}'"
echo ""

echo "3️⃣ Test connexion backend..."
backend_status=$(curl -s -o /dev/null -w "%{http_code}" http://${VPS_IP}:8000/health 2>/dev/null || echo "000")
if [ "$backend_status" = "200" ]; then
    echo "   ✅ Backend accessible (HTTP 200)"
elif [ "$backend_status" = "000" ]; then
    echo "   ⚠️ Backend non accessible (timeout ou connexion refusée)"
else
    echo "   ⚠️ Backend retourne HTTP $backend_status"
fi
echo ""

echo "4️⃣ Test connexion frontend..."
frontend_status=$(curl -s -o /dev/null -w "%{http_code}" http://${VPS_IP}:8501 2>/dev/null || echo "000")
if [ "$frontend_status" = "200" ]; then
    echo "   ✅ Frontend accessible (HTTP 200)"
elif [ "$frontend_status" = "000" ]; then
    echo "   ⚠️ Frontend non accessible (timeout ou connexion refusée)"
else
    echo "   ⚠️ Frontend retourne HTTP $frontend_status"
fi
echo ""

echo "=============================="
echo "✅ Test terminé"
echo ""
echo "📱 URLs de l'application :"
echo "   Frontend : http://${VPS_IP}:8501"
echo "   Backend  : http://${VPS_IP}:8000"
echo ""
echo "🎯 Pour tester le système :"
echo "   1. Ouvrez http://${VPS_IP}:8501 dans votre navigateur"
echo "   2. Allez dans 'Best Bets'"
echo "   3. Cliquez sur 'Lancer le scan'"
echo "   4. Vous devriez voir des picks apparaître !"
echo ""

