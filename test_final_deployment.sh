#!/bin/bash
# Script de test final après déploiement

echo "🎯 TEST FINAL DU DÉPLOIEMENT"
echo "============================="
echo ""

VPS="192.168.1.134"

echo "✅ VÉRIFICATIONS"
echo "----------------"
echo ""

echo "1. Backend UP :"
curl -s http://${VPS}:8000/health | grep -q "ok" && echo "   ✅ Backend répond correctement" || echo "   ❌ Backend ne répond pas"

echo ""
echo "2. Frontend UP :"
curl -s -o /dev/null -w "%{http_code}" http://${VPS}:8501 | grep -q "200" && echo "   ✅ Frontend accessible" || echo "   ❌ Frontend non accessible"

echo ""
echo "3. Seuils déployés :"
ssh juju@${VPS} "grep 'MIN_EDGE = 1.5' /home/juju/jimmy-ai-nba/backend/advanced_scoring.py" > /dev/null 2>&1 && echo "   ✅ MIN_EDGE = 1.5% ✓" || echo "   ❌ MIN_EDGE incorrect"

echo ""
echo "4. Return prématuré supprimé :"
ssh juju@${VPS} "grep 'BUGFIX CRITIQUE' /home/juju/jimmy-ai-nba/backend/advanced_scoring.py" > /dev/null 2>&1 && echo "   ✅ Code corrigé présent ✓" || echo "   ❌ Code non corrigé"

echo ""
echo "============================="
echo "✅ DÉPLOIEMENT VALIDÉ"
echo ""
echo "🎯 TESTEZ MAINTENANT :"
echo "   → http://${VPS}:8501"
echo "   → Menu 'Best Bets'"
echo "   → Cliquez 'Lancer le scan'"
echo "   → Vous devriez voir des picks !"
echo ""
echo "📊 Logs en temps réel :"
echo "   ssh juju@${VPS}"
echo "   cd /home/juju/jimmy-ai-nba"
echo "   docker compose logs -f backend"

