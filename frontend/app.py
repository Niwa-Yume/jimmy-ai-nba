import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

# --- Compat helper: safe_rerun for different Streamlit versions ---
def safe_rerun():
    """Attempt to rerun the Streamlit script in a version-safe way.
    - If st.rerun exists, use it.
    - If st.experimental_rerun exists, use it.
    - Otherwise toggle a session_state flag and stop (user can refresh), to avoid AttributeError.
    """
    # Check for st.rerun (Streamlit >= 1.27)
    if hasattr(st, "rerun"):
        st.rerun()
        return
    
    # Check for st.experimental_rerun (Older Streamlit)
    if hasattr(st, "experimental_rerun"):
        st.experimental_rerun()
        return

    # Fallback: flip a dummy session flag and stop execution so UI updates on next manual refresh.
    st.session_state["__force_rerun_toggle"] = not st.session_state.get("__force_rerun_toggle", False)
    # Provide a friendly message to the user if possible
    try:
        st.info("Le rafraîchissement automatique n'est pas supporté par cette version de Streamlit. Actualisez la page manuellement.")
    except Exception:
        pass
    st.stop()

# Configuration de la page
st.set_page_config(
    page_title="Jimmy.AI - Analyse Joueur",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# URL backend FastAPI
API_URL = "http://127.0.0.1:8000"

# --- STYLING CSS AVANCÉ ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');
    
    * { font-family: 'Inter', sans-serif; }

    /* --- 1. CARTES MATCHS (Liste) --- */
    .match-card {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        padding: 12px 16px;
        margin-bottom: 12px;
        transition: transform 0.1s;
        display: flex;
        justify-content: space-between;
        align-items: center;
        color: #0f172a !important;
    }
    .match-card:hover {
        border-color: #3b82f6;
        transform: scale(1.01);
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .dark .match-card {
        background-color: #1e293b !important;
        border-color: #334155;
        color: #f8fafc !important;
    }
    
    /* --- 2. BADGES --- */
    .impact-badge {
        display: inline-block; padding: 4px 12px; border-radius: 12px;
        font-size: 0.85rem; font-weight: 600; margin-right: 8px; margin-bottom: 8px;
    }
    .badge-green { background: #dcfce7; color: #166534; border: 1px solid #bbf7d0; }
    .badge-red { background: #fee2e2; color: #991b1b; border: 1px solid #fecaca; }
    .badge-blue { background: #dbeafe; color: #1e40af; border: 1px solid #bfdbfe; }
    .badge-yellow { background: #fef9c3; color: #854d0e; border: 1px solid #fde047; }

    /* --- 3. CARTE PRINCIPALE (Cockpit) --- */
    .main-card {
        background: #ffffff !important;
        border-radius: 16px; 
        padding: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); 
        border: 1px solid #e2e8f0;
        color: #0f172a !important;
    }
    .dark .main-card { 
        background: #0f172a !important; 
        border-color: #1e293b;
        color: #f8fafc !important;
    }
    
    /* --- 4. BARRE DE CONTEXTE --- */
    .context-bar {
        display: flex; justify-content: space-between; 
        background: #f8fafc !important;
        padding: 12px; border-radius: 10px; margin-bottom: 15px; 
        border: 1px solid #e2e8f0;
        color: #334155 !important;
    }
    .dark .context-bar { 
        background: #1e293b !important; 
        border-color: #334155;
        color: #cbd5e1 !important;
    }
    .context-item { text-align: center; flex: 1; border-right: 1px solid #cbd5e1; }
    .context-item:last-child { border-right: none; }
    
    .context-label { 
        font-size: 0.75rem; 
        color: #64748b !important; 
        text-transform: uppercase; 
        font-weight: 600;
    }
    .dark .context-label { color: #94a3b8 !important; }

    .context-value { 
        font-size: 1.1rem; 
        font-weight: 800; 
        color: #0f172a !important;
    }
    .dark .context-value { color: #f1f5f9 !important; }
    
    .val-high { color: #16a34a !important; } 
    .val-low { color: #dc2626 !important; }
    
    /* --- 5. TICKET DE JEU PREMIUM --- */
    .bet-ticket {
        background: transparent !important;
        border: 1px solid rgba(100,116,139,0.12);
        padding: 12px 14px;
        border-radius: 8px;
        margin-bottom: 12px;
        color: inherit !important;
        box-shadow: none;
        transition: transform 0.06s ease;
        position: relative;
        overflow: visible;
    }
    .bet-ticket:hover { transform: translateY(-3px); border-color: rgba(59,130,246,0.2); }
    .dark .bet-ticket { background: rgba(255,255,255,0.02) !important; border-color: rgba(255,255,255,0.04); }
    
    .ticket-header {
        display: flex; justify-content: space-between; align-items: center;
        margin-bottom: 12px;
    }
    .ticket-player { font-size: 1.2rem; font-weight: 800; }
    .ticket-match { font-size: 0.9rem; color: #64748b; }
    .dark .ticket-match { color: #94a3b8; }
    
    .ticket-stat {
        font-size: 0.8rem; font-weight: 700; text-transform: uppercase;
        background: #e0f2fe; color: #0369a1; padding: 4px 8px; border-radius: 6px;
    }
    .dark .ticket-stat { background: #075985; color: #e0f2fe; }
    
    .ticket-body {
        display: flex; justify-content: space-between; align-items: flex-end;
    }
    .ticket-line { font-size: 2rem; font-weight: 900; color: #16a34a; line-height: 1; }
    .ticket-odds { font-size: 1rem; color: #64748b; font-weight: 600; }
    
    .ticket-ev-badge {
        background: #16a34a; color: white; padding: 6px 12px; border-radius: 20px;
        font-weight: 800; font-size: 0.9rem; box-shadow: 0 2px 4px rgba(22, 163, 74, 0.3);
    }
    .ticket-ev-gold {
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
        box-shadow: 0 2px 4px rgba(245, 158, 11, 0.4);
    }

    /* --- 6. TEXTES GÉNÉRIQUES --- */
    .sub-text { color: #64748b !important; font-size: 0.9rem; }
    .dark .sub-text { color: #94a3b8 !important; }

</style>
""", unsafe_allow_html=True)

# --- HELPERS ---
def api_get(path, timeout=15):
    try:
        res = requests.get(f"{API_URL}{path}", timeout=timeout)
        if res.ok: return res.json()
    except: return None
    return None

def api_post(path, json=None):
    try:
        res = requests.post(f"{API_URL}{path}", json=json, timeout=10)
        if res.ok: return res.json()
    except: return None
    return None

def fetch_weekly_games():
    data = api_get("/games/week")
    return data.get("games", []) if data else []

def fetch_all_players():
    data = api_get("/players/")
    return data if data else []

def fetch_player_projection(player_id, game_id=None):
    url = f"/projection/{player_id}"
    if game_id: url += f"?game_id={game_id}"
    return api_get(url)

def fetch_lineups(nba_game_id: str):
    return api_get(f"/games/{nba_game_id}/lineups")

def fetch_best_bets():
    return api_get("/analysis/best-bets", timeout=30)

def build_parlay(bets, bet_types=None):
    # build_parlay now expects the frontend to pass already filtered bets
    return api_post("/analysis/build-parlay", json=bets)

def get_headshot_url(nba_player_id: int | None):
    if not nba_player_id: return "https://via.placeholder.com/260x190?text=No+Image"
    return f"https://ak-static.cms.nba.com/wp-content/uploads/headshots/nba/latest/260x190/{nba_player_id}.png"

# --- PAGES ---

def page_matches():
    theme_class = "dark" if st.session_state.get("theme") == "Dark" else ""
    st.markdown(f'<div class="{theme_class}">', unsafe_allow_html=True)

    st.markdown("## Matchs")
    # Force clear top label (ancien texte retiré)

    col1, col2 = st.columns([3, 1])
    with col1:
        period = st.selectbox("Période", ["Aujourd'hui", "Cette semaine", "Tous"], index=1, label_visibility="collapsed")
    with col2:
        if st.button("🔄 Actualiser", use_container_width=True):
            st.session_state.games = fetch_weekly_games()
            safe_rerun()

    # Récupérer et normaliser la liste des matchs
    games = st.session_state.get("games")
    if not games:
        games = fetch_weekly_games() or []
        st.session_state.games = games

    # Si le backend a renvoyé quelque chose d'inattendu, afficher pour debug
    if not isinstance(games, list):
        st.error("Format inattendu reçu pour les matchs (attendu une liste). Voir debug ci‑dessous.")
        with st.expander("Debug: payload brut /games/week"):
            st.write(games)
        st.markdown('</div>', unsafe_allow_html=True)
        return

    today = datetime.now().date().isoformat()
    if period == "Aujourd'hui":
        games = [g for g in games if g.get("game_date") == today]
    
    # Normaliser et trier
    normalized = []
    for g in games:
        if not isinstance(g, dict):
            continue
        # ensure keys exist
        g.setdefault('game_date', g.get('game_date') or g.get('date') or 'N/A')
        g.setdefault('game_time', g.get('game_time') or g.get('time') or '')
        g.setdefault('home_team', g.get('home_team') or g.get('home') or g.get('home_team_code'))
        g.setdefault('away_team', g.get('away_team') or g.get('away') or g.get('away_team_code'))
        normalized.append(g)

    # Group by date and sort dates ascending
    grouped = {}
    for g in normalized:
        grouped.setdefault(g.get("game_date", "N/A"), []).append(g)
    grouped = dict(sorted(grouped.items(), key=lambda x: x[0]))

    for date_str, day_games in sorted(grouped.items()):
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            date_nice = date_obj.strftime("%A %d %B")
        except:
            date_nice = date_str
            
        st.markdown(f"### 📅 {date_nice}")

        for i in range(0, len(day_games), 2):
            cols = st.columns(2)
            for j, col in enumerate(cols):
                if i + j >= len(day_games): continue
                g = day_games[i + j]
                
                time_str = g.get('game_time', '')
                try:
                    if 'T' in time_str:
                        dt = datetime.fromisoformat(time_str.replace('Z', ''))
                        time_str = dt.strftime('%H:%M')
                except: pass

                with col:
                    # Carte HTML avec couleurs forcées
                    st.markdown(f"""
                    <div class="match-card">
                        <div style="display:flex; align-items:center; gap:15px;">
                            <div style="font-weight:800; font-size:1.1rem;">{g['away_team']}</div>
                            <div style="color:#94a3b8; font-weight:600;">@</div>
                            <div style="font-weight:800; font-size:1.1rem;">{g['home_team']}</div>
                        </div>
                        <div style="text-align:right;">
                            <div style="font-weight:700; color:#475569;">{time_str}</div>
                            <div style="font-size:0.8rem; color:#94a3b8;">{g.get('arena','')}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    if st.button("📊 Analyser", key=f"btn_m_{g['nba_game_id']}", use_container_width=True):
                        st.session_state.selected_match = g
                        st.session_state.page = "players"
                        safe_rerun()

    st.markdown('</div>', unsafe_allow_html=True)

def page_players():
    theme_class = "dark" if st.session_state.get("theme") == "Dark" else ""
    st.markdown(f'<div class="{theme_class}">', unsafe_allow_html=True)

    match = st.session_state.get("selected_match")
    if not match: st.error("Erreur sélection"); return
    if st.button("⬅️ Retour Calendrier"): st.session_state.page = "matches"; safe_rerun()

    st.markdown(f"## {match['away_team']} @ {match['home_team']}")
    
    cache_key = f"lineups::{match.get('nba_game_id')}"
    if "_lineups_cache" not in st.session_state: st.session_state._lineups_cache = {}
    lineups = st.session_state._lineups_cache.get(cache_key)
    
    if not lineups:
        with st.spinner("Récupération des effectifs..."):
            lineups = fetch_lineups(match["nba_game_id"])
        if lineups: st.session_state._lineups_cache[cache_key] = lineups
    
    if not lineups: st.warning("Effectifs non disponibles."); return

    c1, c2 = st.columns(2)
    for col, team, roster in [(c1, lineups.get('away_team'), lineups.get('away_roster')), (c2, lineups.get('home_team'), lineups.get('home_roster'))]:
        with col:
            st.subheader(f"{team}")
            if not roster: st.info("Aucun joueur listé.")
            for p in roster or []:
                # Utilisation de st.container pour le style natif, mais on pourrait utiliser du HTML custom
                # Utiliser st.container natif sans background noir
                with st.container():
                     cl1, cl2 = st.columns([3, 1])
                     with cl1:
                         st.markdown(f"**{p['full_name']}**")
                         st.caption(f"{p.get('position')} • {p.get('injury_status','OK')}")
                     with cl2:
                         if p.get('id') and st.button("Go", key=f"p_{p['id']}"):
                            st.session_state.selected_player_id = p['id']
                            st.session_state.page = "player_detail"
                            safe_rerun()
    st.markdown('</div>', unsafe_allow_html=True)

def page_players_index():
    st.markdown("## 👤 Annuaire Joueurs")
    q = st.text_input("Rechercher un joueur")
    if st.button("Lancer la recherche"):
        st.session_state.players_index = fetch_all_players()
        safe_rerun()

    players = st.session_state.get("players_index", [])
    if players:
        filtered = [p for p in players if q.lower() in (p.get("full_name") or "").lower()]
        st.caption(f"{len(filtered)} joueurs trouvés")
        for p in filtered[:20]:
            if st.button(f"{p['full_name']} ({p.get('position')})", key=f"s_{p['id']}"):
                st.session_state.selected_player_id = p['id']
                st.session_state.page = "player_detail"
                safe_rerun()

def page_player_detail():
    theme_class = "dark" if st.session_state.get("theme") == "Dark" else ""
    st.markdown(f'<div class="{theme_class}">', unsafe_allow_html=True)

    pid = st.session_state.get("selected_player_id")
    match = st.session_state.get("selected_match")
    game_id = match.get("nba_game_id") if match else None

    if not pid: st.error("Erreur ID"); return
    if st.button("⬅️ Retour"): st.session_state.page = "players"; safe_rerun()

    with st.spinner("🧠 Analyse complète en cours..."):
        data = fetch_player_projection(pid, game_id)

    if not data or "projections" not in data: st.error("Données indisponibles."); return

    p_name = data.get("player")
    opp = data.get("opponent", "N/A")
    loc = data.get("location", "N/A")
    headshot = get_headshot_url(data.get("nba_player_id"))
    
    c1, c2 = st.columns([1, 4])
    with c1: st.image(headshot, width=120)
    with c2:
        st.title(p_name)
        st.markdown(f"**{data.get('position')}** • {'🏠 Domicile' if loc == 'Home' else '✈️ Extérieur'} vs **{opp}**")
        st.info(f"🤖 **Jimmy :** {data.get('jimmy_advice')}")

    st.markdown("---")

    tabs = st.tabs(["🏀 Points", "🔄 Rebonds", "🎯 Passes", "👌 3-Points", "🥷 Steals", "🧱 Blocks"])
    keys = ["points", "rebounds", "assists", "three_points_made", "steals", "blocks"]

    for tab, key in zip(tabs, keys):
        stat = data.get("projections", {}).get(key)
        with tab:
            if not stat: st.warning("Pas de data"); continue

            # Badges
            factors_html = ""
            pace = stat.get('pace_factor', 1.0)
            if pace > 1.02: factors_html += '<span class="impact-badge badge-blue">⚡️ Rythme Rapide</span>'
            elif pace < 0.98: factors_html += '<span class="impact-badge badge-red">🐢 Rythme Lent</span>'
            
            defense = stat.get('defensive_factor', 1.0)
            if defense > 1.05: factors_html += '<span class="impact-badge badge-green">🟢 Défense Perméable</span>'
            elif defense < 0.95: factors_html += '<span class="impact-badge badge-red">🛡️ Défense Elite</span>'
            
            usage = stat.get('offensive_boost', 1.0)
            if usage > 1.05: factors_html += '<span class="impact-badge badge-yellow">🚀 Boost Usage</span>'
            
            ema = stat.get('ema', 0)
            season = stat.get('recent_avg', 0)
            if ema > season * 1.1: factors_html += '<span class="impact-badge badge-green">🔥 En Feu</span>'
            
            st.markdown(f"<div>{factors_html}</div>", unsafe_allow_html=True)

            # Contexte
            v_season = stat.get('season_avg', stat.get('recent_avg', 0))
            v_form = stat.get('ema', 0)
            v_loc = stat.get('loc_avg', 'N/A')
            v_h2h = stat.get('h2h_avg', 'N/A')
            
            def get_color_class(val, ref):
                try: return "val-high" if float(val) > float(ref) else "val-low"
                except: return ""

            st.markdown(f"""
            <div class="context-bar">
                <div class="context-item"><div class="context-label">Saison</div><div class="context-value">{v_season}</div></div>
                <div class="context-item"><div class="context-label">Forme</div><div class="context-value {get_color_class(v_form, v_season)}">{v_form}</div></div>
                <div class="context-item"><div class="context-label">{'Dom' if loc == 'Home' else 'Ext'}</div><div class="context-value {get_color_class(v_loc, v_season)}">{v_loc}</div></div>
                <div class="context-item"><div class="context-label">vs {opp}</div><div class="context-value {get_color_class(v_h2h, v_season)}">{v_h2h}</div></div>
            </div>
            """, unsafe_allow_html=True)

            # Carte Principale
            with st.container():
                st.markdown('<div class="main-card">', unsafe_allow_html=True)
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.markdown('<div class="sub-text" style="text-align:center;">🎯 PRÉVISION JIMMY</div>', unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align:center; font-size:2.5rem; font-weight:800;'>{stat.get('projection')}</div>", unsafe_allow_html=True)
                with c2:
                    bookmaker = stat.get('bookmaker') or 'N/A'
                    source = "Simulation" if stat.get('is_simulation') else f"Cote {bookmaker}"
                    st.markdown(f'<div class="sub-text" style="text-align:center;">🏦 LIGNE {bookmaker.upper()}</div>', unsafe_allow_html=True)
                    st.markdown(f"<div style='text-align:center; font-size:2.5rem; font-weight:800; color:#3b82f6;'>{stat.get('betting_line')}</div>", unsafe_allow_html=True)
                    st.markdown(f"<div class='sub-text' style='text-align:center; font-size:0.8rem;'>{source}</div>", unsafe_allow_html=True)
                with c3:
                    # Protéger contre betting_line None (absence de cotes) pour éviter TypeError
                    proj_val = stat.get('projection') if stat.get('projection') is not None else 0
                    bet_line_val = stat.get('betting_line')
                    try:
                        delta = proj_val - bet_line_val if bet_line_val is not None else None
                    except Exception:
                        delta = None
                    conf = stat.get('confidence', '')
                    st.markdown('<div class="sub-text" style="text-align:center;">VERDICT</div>', unsafe_allow_html=True)

                    verdict_color = "#f59e0b"  # Orange
                    verdict_text = "PASSE"
                    if "🔥" in conf:
                        verdict_color = "#22c55e"
                        verdict_text = "FONCE !"
                    elif "✅" in conf:
                        verdict_color = "#22c55e"
                        verdict_text = "BON PLAN"
                    elif "❌" in conf:
                        verdict_color = "#ef4444"
                        verdict_text = "ÉVITER"

                    st.markdown(f"<div style='text-align:center; font-size:1.5rem; font-weight:900; color:{verdict_color};'>{verdict_text}</div>", unsafe_allow_html=True)
                    if delta is not None:
                        st.markdown(f"<div style='text-align:center; font-weight:600;'>Marge : {delta:+.1f}</div>", unsafe_allow_html=True)
                    else:
                        st.markdown(f"<div style='text-align:center; font-weight:600;'>Marge : N/A (pas de ligne)</div>", unsafe_allow_html=True)
                st.markdown('</div>', unsafe_allow_html=True)

            # Probabilités
            milestones = stat.get("milestones", [])
            if milestones:
                st.markdown("#### 📊 Probabilités")
                df_ms = pd.DataFrame([{"Palier": m['value'], "Probabilité": m['probability']/100} for m in milestones])
                st.dataframe(df_ms, use_container_width=True, hide_index=True, column_config={"Probabilité": st.column_config.ProgressColumn(format="%.0f%%", min_value=0, max_value=1)})

    st.markdown("---")
    st.markdown("### 📅 Historique Récent")
    last_games = data.get("last_games", [])
    if last_games:
        df_log = pd.DataFrame(last_games)
        df_log = df_log.rename(columns={"date": "Date", "points": "PTS", "rebounds": "REB", "assists": "AST", "3pm": "3PM", "steals": "STL", "blocks": "BLK", "min": "MIN"})
        st.dataframe(df_log, use_container_width=True, hide_index=True)
    else:
        st.info("Pas d'historique disponible.")
    
    st.markdown('</div>', unsafe_allow_html=True)

def page_best_bets():
    theme_class = "dark" if st.session_state.get("theme") == "Dark" else ""
    st.markdown(f'<div class="{theme_class}">', unsafe_allow_html=True)
    
    st.markdown("## 🏆 Carte de Jeu (Top Picks)")
    
    # Options du scan : marchés et nombre max de joueurs par équipe
    markets_map = {
        "Points": "points",
        "Rebonds": "rebounds",
        "Passes": "assists",
        "3-Points": "three_points_made"
    }
    st.markdown("### Paramètres du Scan")
    selected_display = st.multiselect("Marchés à analyser", list(markets_map.keys()), default=["3-Points", "Points", "Passes", "Rebonds"])
    # Enregistrer la sélection des marchés dans la session pour usage après le scan
    st.session_state.selected_display = selected_display

    if st.button("🔄 Lancer le Scan (Arrière-plan)", use_container_width=True):
        # Transformer la sélection en clefs internes
        markets = [markets_map[m] for m in selected_display]
        payload = {"markets": markets}
        resp = api_post("/analysis/start-scan", json=payload)
        if resp:
            st.session_state.scan_job_id = resp.get("job_id")
            st.session_state.scan_markets = markets
            safe_rerun()

    job_id = st.session_state.get("scan_job_id")
    
    if job_id:
        # Poll visuel : interroger l'endpoint plusieurs fois (non-bloquant pour server) et afficher la progression
        progress_bar = st.progress(0)
        status_text = st.empty()
        max_polls = 30  # Augmenté pour mieux correspondre au temps réel
        poll_interval = 2  # seconds
        final_res = None
        for i in range(max_polls):
            res = api_get(f"/analysis/scan-results/{job_id}")
            if not res:
                status_text.text(f"🔄 Vérification du statut... ({i+1}/{max_polls})")
                progress_bar.progress(min(i / max_polls, 0.9))  # Max 90% si pas de réponse
                time.sleep(poll_interval)
                continue
            # Support backend meta indicating odds API is disabled/exhausted
            meta = res.get('meta', {}) if isinstance(res, dict) else {}
            if meta and meta.get('odds_disabled'):
                # Stop polling and inform the user
                status_text.error("⚠️ Analyse interrompue : les clés API de cotes sont présentes mais épuisées. Impossible de récupérer des cotes fiables.")
                # Store meta in session for UI
                st.session_state.scan_meta = meta
                st.session_state.best_bets = []
                st.session_state.scan_job_id = None
                final_res = None
                break
            status = res.get("status")
            progress = res.get("progress", 0)
            data = res.get("data", [])
            message = res.get("message", "")
            if status == "running":
                status_text.text(f"⏳ Analyse en cours... {len(data)} opportunités détectées provisoirement")
                progress_bar.progress(progress / 100)
                # Small sleep before next poll
                time.sleep(poll_interval)
                continue
            elif status == "complete":
                status_text.text(f"✅ Analyse terminée — {len(data)} opportunités trouvées")
                progress_bar.progress(1.0)
                final_res = res
                break
            else:
                status_text.text(f"🔍 Statut du job : {status}")
                progress_bar.progress(progress / 100)
                time.sleep(poll_interval)
                continue

        if final_res:
            message = final_res.get("message", "")
            if message:
                st.info(message)
            # Cast and sanitize bets for stability (ensure native types)
            raw_bets = final_res.get("data", []) or []
            sanitized = []
            for b in raw_bets:
                try:
                    b_clean = dict(b)
                    # Ensure numeric types
                    if b_clean.get('odds') is not None:
                        b_clean['odds'] = float(b_clean['odds'])
                    if b_clean.get('ev') is not None:
                        b_clean['ev'] = float(b_clean['ev'])
                    if b_clean.get('projection') is not None:
                        b_clean['projection'] = float(b_clean['projection'])
                    sanitized.append(b_clean)
                except Exception:
                    continue
            # Separate bets that have real odds/EV from projection-only entries (no odds)
            bets_with_odds = [x for x in sanitized if x.get('odds') is not None and x.get('ev') is not None and x.get('ev') > 0]
            bets_projection_only = [x for x in sanitized if x.get('odds') is None]
            # Store both lists in session; UI will show odds bets first then projection-only
            st.session_state.best_bets = bets_with_odds
            st.session_state.projection_only_bets = bets_projection_only
            st.session_state.scan_job_id = None
            safe_rerun()
        else:
            # pas de résultat final après polling : garder le job_id pour refresh manuel
            status_text.warning("Le scan est toujours en cours ou n'a pas renvoyé de résultat final dans le temps imparti. Appuyez sur '🔁 Rafraîchir l'état' si nécessaire.")
            if st.button("🔁 Rafraîchir l'état"):
                safe_rerun()

    bets_all = st.session_state.get("best_bets", [])
    # Determine selected markets (map display names to internal keys)
    selected_display = st.session_state.get('selected_display', ["3-Points", "Points", "Passes", "Rebonds"])
    display_to_key = {"Points": "points", "Rebonds": "rebounds", "Passes": "assists", "3-Points": "three_points_made"}
    selected_markets = [display_to_key.get(d) for d in selected_display if d in display_to_key]
    # Filter bets to only include selected markets
    if selected_markets:
        bets = [b for b in bets_all if b.get('market') in selected_markets]
    else:
        bets = bets_all

    # Enrichissement UX : drapeaux et tri par score décroissant
    for b in bets:
        b.setdefault('injury_status', 'UNKNOWN')
        b.setdefault('odds_source', 'snapshot')
        b['score'] = float(b.get('ev') or 0.0)
        b['risk_flag'] = 'INJ' if b['injury_status'] and b['injury_status'] not in ['HEALTHY', 'ACTIVE'] else ''
        b['confidence_flag'] = 'HIGH' if b['score'] >= 75 else ('MED' if b['score'] >= 60 else 'LOW')
    bets = sorted(bets, key=lambda x: x.get('score', 0), reverse=True)

    st.markdown(f"#### 🎯 Opportunités détectées : {len(bets)}")

    # Limiter l'affichage à 15 cartes pour simplicité; bouton pour tout voir
    show_all = st.checkbox("Afficher tous les picks", value=False)
    bets_to_show = bets if show_all else bets[:15]

    if 'selected_bets_ids' not in st.session_state:
        st.session_state.selected_bets_ids = set()

    col_sel_left, col_sel_right = st.columns([1, 3])
    with col_sel_left:
        if st.button("Tout sélectionner"):
            st.session_state.selected_bets_ids = {f"{b.get('player_id')}|{b.get('market')}|{b.get('game_id')}" for b in bets_to_show}
            safe_rerun()
        if st.button("Tout désélectionner"):
            st.session_state.selected_bets_ids = set()
            safe_rerun()
    with col_sel_right:
        st.write("Sélectionnez les paris à inclure (top 15 par défaut).")

    for b in bets_to_show:
        bet_key = f"{b.get('player_id')}|{b.get('market')}|{b.get('game_id')}"
        checked = bet_key in st.session_state.selected_bets_ids
        with st.container():
            cols = st.columns([0.1, 0.6, 0.3])
            with cols[0]:
                new_val = st.checkbox("Sélection", value=checked, key=f"chk_{bet_key}", label_visibility="collapsed")
                if new_val:
                    st.session_state.selected_bets_ids.add(bet_key)
                else:
                    st.session_state.selected_bets_ids.discard(bet_key)
            with cols[1]:
                st.markdown(f"**{b.get('player')}** — {b.get('market').upper()} {b.get('line')} @ {b.get('odds')} (src: {b.get('odds_source') or 'n/a'})")
                st.markdown(f"Proj: {b.get('projection')} | Conf: {b.get('confidence')} | Score: {b.get('score'):.0f}")
                if b.get('risk_flag'):
                    st.markdown(f"🚑 Statut blessure: {b.get('injury_status')}")
            with cols[2]:
                st.markdown(f"EV / Score: **{b.get('score'):.0f}**")
                st.markdown(f"{b.get('team')} vs {b.get('opponent')}")
                st.markdown(f"Type: {b.get('bet_type')}")

    selected_bets = [b for b in bets if f"{b.get('player_id')}|{b.get('market')}|{b.get('game_id')}" in st.session_state.selected_bets_ids]

    st.markdown("### 🧮 Votre ticket")
    if selected_bets:
        col_left, col_right = st.columns([3,1])
        with col_left:
            for b in selected_bets:
                st.markdown(f"- {b.get('player')} {b.get('market')} {b.get('line')} @ {b.get('odds')} ({b.get('team')} vs {b.get('opponent')})")
        with col_right:
            if st.button("Construire le parlay"):
                resp = build_parlay(selected_bets)
                st.write(resp)
    else:
        st.info("Sélectionnez des picks pour construire le ticket.")

    st.markdown('</div>', unsafe_allow_html=True)

# --- ROUTER ---
def main():
    if 'page' not in st.session_state: st.session_state.page = "matches"
    
    with st.sidebar:
        st.title("🏀 Jimmy.AI")
        if st.button("🏆 Carte de Jeu"): st.session_state.page = "best_bets"; safe_rerun()
        if st.button("🏠 Matchs"): st.session_state.page = "matches"; safe_rerun()
        if st.button("👤 Joueurs"): st.session_state.page = "players_index"; safe_rerun()
        st.markdown("---")
        theme = st.radio("Thème", ["Light", "Dark"], horizontal=True)
        if theme != st.session_state.get("theme"):
            st.session_state.theme = theme
            safe_rerun()

    if st.session_state.page == "matches": page_matches()
    elif st.session_state.page == "players": page_players()
    elif st.session_state.page == "player_detail": page_player_detail()
    elif st.session_state.page == "players_index": page_players_index()
    elif st.session_state.page == "best_bets": page_best_bets()

if __name__ == "__main__":
    main()
