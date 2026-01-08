# 🔧 FIX : Problème de 0 Picks (Anciennement 101 picks)

## 📋 Diagnostic

**Problème identifié :** Les seuils de filtrage étaient trop restrictifs, ce qui empêchait tous les picks de passer le filtre.

### Seuils problématiques (AVANT)
- `MIN_EDGE = 6.0%` - **TROP ÉLEVÉ** pour la NBA
- `MIN_SCORE = 55` - Score minimum trop strict
- `MIN_SAMPLE_SIZE = 10` - Échantillon trop grand requis
- Pénalités blessures trop sévères (DOUBTFUL éliminé à 100%)

## ✅ Corrections Appliquées

### 1. Seuils ajustés dans `backend/advanced_scoring.py`

```python
# AVANT
MIN_SCORE = 55  # Trop strict
MIN_EDGE = 6.0  # Edge irréaliste pour NBA
MIN_SAMPLE_SIZE = 10  # Trop de matchs requis

# APRÈS
MIN_SCORE = 50  # Équilibré (50/100)
MIN_EDGE = 3.5  # Réaliste pour NBA (3.5%)
MIN_SAMPLE_SIZE = 8  # Plus flexible
```

### 2. Pénalités blessures assouplies

```python
# AVANT
'DOUBTFUL': 0.3,      # Trop pénalisé
'QUESTIONABLE': 0.7,  
'DAY_TO_DAY': 0.85,   
'GTD': 0.7,

# APRÈS
'DOUBTFUL': 0.5,      # Pénalisé mais peut passer
'QUESTIONABLE': 0.85, # Très légère pénalité
'DAY_TO_DAY': 0.95,   # Presque aucune pénalité (courant NBA)
'GTD': 0.85,          # Légère pénalité
```

### 3. Logique de filtrage améliorée

**AVANT :** Éliminait automatiquement OUT + DOUBTFUL
```python
risky_statuses = ['OUT', 'DOUBTFUL']
if injury_status in risky_statuses:
    return False
```

**APRÈS :** Élimine uniquement OUT, laisse le score décider pour DOUBTFUL
```python
if injury_status and str(injury_status).upper() == 'OUT':
    return False
```

## 🚀 Déploiement

Le fix a été déployé sur le VPS `juju@192.168.1.134` avec succès.

**Containers redémarrés :**
- ✅ `jimmy_db` - PostgreSQL 15
- ✅ `jimmy_backend` - FastAPI (port 8000)
- ✅ `jimmy_frontend` - Streamlit (port 8501)
- ✅ `jimmy_caddy` - Reverse proxy (ports 80/443)

## 🎯 Résultats Attendus

Avec ces changements, vous devriez maintenant avoir :
- **Plus de picks détectés** (retour vers ~101 picks ou plus)
- **Qualité préservée** grâce au scoring avancé (MIN_SCORE = 50)
- **Edge réaliste** (3.5% au lieu de 6%)
- **Flexibilité sur les blessures** (DAY_TO_DAY, QUESTIONABLE ne pénalisent presque pas)

## 📊 Vérification

Pour vérifier que le système fonctionne :
1. Connectez-vous à l'interface : `http://192.168.1.134` ou `https://votre-domaine`
2. Allez dans la section "Best Bets"
3. Lancez un scan
4. Vous devriez maintenant voir plusieurs picks apparaître

## 🔍 Monitoring

Pour voir les logs en temps réel sur le VPS :
```bash
ssh juju@192.168.1.134
cd /home/juju/jimmy-ai-nba
docker compose logs -f backend
```

## 📝 Note Importante

L'edge de 6% était effectivement **irréaliste pour la NBA**. Dans les paris sportifs NBA professionnels :
- Un edge de **3-4% est considéré comme excellent**
- Un edge de **5-6% est rare**
- Un edge de **>8% est exceptionnel**

C'est pourquoi le seuil a été abaissé à **3.5%** pour détecter les vraies opportunités de value.

---

**Date du fix :** 8 janvier 2026
**Version :** 1.0
**Status :** ✅ Déployé et actif

