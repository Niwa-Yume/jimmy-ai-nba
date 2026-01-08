#!/bin/bash
# Script de test post-fix critique

echo "🧪 TEST DU FIX CRITIQUE"
echo "========================"
echo ""

VPS="juju@192.168.1.134"

echo "1️⃣ Vérification des seuils dans le code déployé..."
ssh $VPS "grep -n 'MIN_EDGE\|MIN_SCORE\|MIN_SAMPLE' /home/juju/jimmy-ai-nba/backend/advanced_scoring.py | head -3"
echo ""

echo "2️⃣ Vérification que le return prématuré a été supprimé..."
check=$(ssh $VPS "grep -A2 'edge = abs(projection' /home/juju/jimmy-ai-nba/backend/advanced_scoring.py | grep 'if edge < self.MIN_EDGE:' | wc -l")
if [ "$check" -eq "0" ]; then
    echo "   ✅ Return prématuré supprimé (c'était le bug !)"
else
    echo "   ❌ Return prématuré encore présent !"
fi
echo ""

echo "3️⃣ État du container backend..."
ssh $VPS "docker ps --filter name=jimmy_backend --format '{{.Names}}: {{.Status}}'"
echo ""

echo "4️⃣ Logs récents du backend (dernières 20 lignes)..."
ssh $VPS "docker compose -f /home/juju/jimmy-ai-nba/docker-compose.yml logs backend --tail 20 | tail -10"
echo ""

echo "========================"
echo "✅ Test terminé"
echo ""
echo "🎯 Pour tester maintenant :"
echo "   1. Ouvrez http://192.168.1.134:8501"
echo "   2. Section 'Best Bets'"
echo "   3. Cliquez 'Lancer le scan'"
echo "   4. Vous devriez voir des picks apparaître !"
echo ""
echo "📊 Pour suivre les logs en temps réel :"
echo "   ssh $VPS"
echo "   cd /home/juju/jimmy-ai-nba"
echo "   docker compose logs -f backend"

