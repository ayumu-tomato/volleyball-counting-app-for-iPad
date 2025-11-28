import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from streamlit_image_coordinates import streamlit_image_coordinates
import io
from PIL import Image
import datetime
import xlsxwriter
import time
import json
import os

# ==========================================
# 1. 設定 & CSS (iPad最適化 Ver 7.0)
# ==========================================
st.set_page_config(page_title="Volleyball Scouter Ver.7.0", layout="wide")

st.markdown("""
<style>
    .block-container { padding-top: 4rem; padding-bottom: 6rem; }
    
    div.stButton > button {
        width: 100%; height: 65px; font-weight: bold; font-size: 22px;
        border-radius: 12px; margin-bottom: 5px; touch-action: manipulation;
    }
    div.stDownloadButton > button {
        background-color: #FF4B4B; color: white; height: 80px; font-size: 24px;
        border: 2px solid white; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .score-board { font-size: 40px; font-weight: 900; text-align: center; background: #333; color: white; padding: 5px; border-radius: 8px; }
    .input-card { background-color: #f8f9fa; padding: 10px; border-radius: 15px; border: 2px solid #e9ecef; }
    .step-header { font-size: 20px; font-weight: bold; color: #4c78a8; margin-bottom: 10px; border-bottom: 2px solid #4c78a8; }
    .rot-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 4px; text-align: center; font-weight: bold; font-size: 14px; }
    .rot-cell { border: 1px solid #555; padding: 8px; background: white; border-radius: 6px; }
    .rot-front { background: #ffebeb; }
    .rot-server { border: 3px solid red; color: red; font-weight: 900; }
    
    /* ロードボタンを目立たせる */
    .load-btn > button { background-color: #28a745; color: white; border: 2px solid #fff; }
</style>
""", unsafe_allow_html=True)

# セッション初期化
defaults = {
    'stage': 0, 'roster_cursor': 0, 'temp_roster': [], 'scout_step': 0,
    'set_name': '1', 'video_url': '', 'liberos': [], 'rotation': [], 'score': [0, 0], 'phase': 'R',
    'current_input_data': {}, 'data_log': [], 'points': [], 'setter_counts': {},
    'key_map': 0, 'time_buffer': "",
    'combo_counts': {'X5': 10, 'V5': 5, '1': 8, '2': 4, 'A': 3, 'B': 3, 'C': 2, 'P': 6},
    'key_roster': 0 
}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

# ==========================================
# 2. 保存・復元ロジック (Auto Save/Load)
# ==========================================
SAVE_DATA_FILE = "autosave_data.csv"
SAVE_STATE_FILE = "autosave_state.json"

def auto_save():
    """現在の状態をファイルに保存する"""
    # 1. データログの保存
    if len(st.session_state.data_log) > 0:
        pd.DataFrame(st.session_state.data_log).to_csv(SAVE_DATA_FILE, index=False)
    
    # 2. ゲーム状態（スコア、ローテなど）の保存
    state_data = {
        "score": st.session_state.score,
        "rotation": st.session_state.rotation,
        "phase": st.session_state.phase,
        "set_name": st.session_state.set_name,
        "video_url": st.session_state.video_url,
        "liberos": st.session_state.liberos,
        "setter_counts": st.session_state.setter_counts,
        "combo_counts": st.session_state.combo_counts,
        "stage": st.session_state.stage
    }
    with open(SAVE_STATE_FILE, 'w') as f:
        json.dump(state_data, f)

def load_autosave():
    """保存ファイルから状態を復元する"""
    try:
        # データログ復元
        if os.path.exists(SAVE_DATA_FILE):
            df = pd.read_csv(SAVE_DATA_FILE)
            st.session_state.data_log = df.to_dict('records')
        
        # ゲーム状態復元
        if os.path.exists(SAVE_STATE_FILE):
            with open(SAVE_STATE_FILE, 'r') as f:
                state_data = json.load(f)
                st.session_state.score = state_data["score"]
                st.session_state.rotation = state_data["rotation"]
                st.session_state.phase = state_data["phase"]
                st.session_state.set_name = state_data["set_name"]
                st.session_state.video_url = state_data["video_url"]
                st.session_state.liberos = state_data["liberos"]
                st.session_state.setter_counts = state_data["setter_counts"]
                st.session_state.combo_counts = state_data["combo_counts"]
                st.session_state.stage = 6 # 強制的にメイン画面へ
                
        st.toast("復元しました！ (Resumed)", icon="📂")
        st.rerun()
    except Exception as e:
        st.error(f"復元に失敗しました: {e}")

# ==========================================
# 3. ロジック関数
# ==========================================
def get_zone(x, y, w, h):
    cx, cy = (x / w) * 9, (1 - (y / h)) * 18 
    if 0 <= cy < 9: # 自コート
        r, c = int(cy//3), int(cx//3)
        if r==0: return [5,6,1][c]
        if r==1: return [7,8,9][c]
        if r==2: return [4,3,2][c]
    elif 9 <= cy <= 18: # 相手コート
        is_front = (cy < 13.5)
        col_img = int(cx // 3)
        if is_front: return [2,3,4][col_img]
        else: return [1,6,5][col_img]
    return 0

def create_court_img(points):
    fig, ax = plt.subplots(figsize=(3, 6))
    ax.add_patch(patches.Rectangle((0, 0), 9, 18, fc='#FFCC99', ec='black', lw=2))
    ax.plot([0,9], [9,9], c='red', lw=3)
    ax.plot([0,9], [6,6], c='black', lw=1); ax.plot([0,9], [12,12], c='black', lw=1)
    ax.plot([0,9], [13.5, 13.5], c='gray', ls=':', lw=0.5)
    ax.plot([3,3], [9,18], c='gray', ls=':', lw=0.5); ax.plot([6,6], [9,18], c='gray', ls=':', lw=0.5)

    for i, p in enumerate(points):
        px, py = (p[0]/230)*9, (1-(p[1]/460))*18
        col = "blue" if i==0 else "red"
        lbl = "S" if i==0 else "E"
        ax.scatter(px, py, s=150, c=col, zorder=10, edgecolors='white')
        ax.text(px, py, lbl, color='white', ha='center', va='center', fontweight='bold', fontsize=8)
        if i==1: 
            sx, sy = (points[0][0]/230)*9, (1-(points[0][1]/460))*18
            ax.arrow(sx, sy, px-sx, py-sy, width=0.15, color='gray', alpha=0.5)
    ax.set_xlim(0, 9); ax.set_ylim(0, 18); ax.axis('off')
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
    buf.seek(0)
    return Image.open(buf)

def format_time(val):
    s = str(val).strip()
    if len(s) == 0: return "00:00"
    v = int(s)
    if len(s) <= 2: return f"00:{v:02d}"
    sec = int(s[-2:]); min_ = int(s[:-2])
    return f"{min_:02d}:{sec:02d}"

def time_to_sec(t_str):
    if ':' not in t_str: return 0
    m, s = t_str.split(':')
    return int(m)*60 + int(s)

def rotate_team():
    r = st.session_state.rotation
    st.session_state.rotation = [r[-1]] + r[:-1]
    auto_save() # 保存

def update_score(winner):
    if winner == 'my':
        st.session_state.score[0] += 1
        if st.session_state.phase == 'R':
            rotate_team()
            st.toast("Sideout!", icon="⭕")
        else:
            st.toast("Break!", icon="⭕")
        st.session_state.phase = 'S'
    elif winner == 'op':
        st.session_state.score[1] += 1
        st.session_state.phase = 'R'
        st.toast("Op Point", icon="❌")
    auto_save() # 保存

def count_setter_usage(name):
    if name and name != "Direct/Two":
        st.session_state.setter_counts[name] = st.session_state.setter_counts.get(name, 0) + 1

def count_combo_usage(combo):
    if combo:
        st.session_state.combo_counts[combo] = st.session_state.combo_counts.get(combo, 0) + 1

def commit_record(quality, winner=None):
    curr = st.session_state.current_input_data
    if curr.get('skill') == 'A':
        count_combo_usage(curr.get('combo', ''))

    s_z, e_z = "", ""
    if len(st.session_state.points)>=1: s_z = get_zone(st.session_state.points[0][0], st.session_state.points[0][1], 230, 460)
    if len(st.session_state.points)>=2: e_z = get_zone(st.session_state.points[1][0], st.session_state.points[1][1], 230, 460)
    
    final_row = {
        "set": st.session_state.set_name,
        "score": f"{st.session_state.score[0]}-{st.session_state.score[1]}",
        "phase": st.session_state.phase,
        "setter": curr.get('setter',''), "player": curr.get('player',''),
        "skill": curr.get('skill',''), "combo": curr.get('combo',''),
        "quality": quality,
        "start_zone": s_z, "end_zone": e_z,
        "memo": "", "video_url": st.session_state.video_url,
        "video_time": time_to_sec(curr.get('time',''))
    }
    st.session_state.data_log.append(final_row)
    
    if winner: update_score(winner)
    else:
        skill = curr.get('skill','')
        if (skill in ['A','B','S'] and quality=='#') or (skill=='A' and quality=='T'): update_score('my')
        elif quality == '^': update_score('op')
        else: st.toast("Saved", icon="✅")

    # リセット
    st.session_state.points = []
    st.session_state.current_input_data = {}
    st.session_state.scout_step = 0
    st.session_state.key_map += 1
    st.session_state.time_buffer = "" 
    
    auto_save() # ★ここで自動保存
    st.rerun()

def get_sorted_setters():
    candidates = st.session_state.rotation + [l for l in st.session_state.liberos if l]
    sorted_list = sorted(candidates, key=lambda n: st.session_state.setter_counts.get(n, 0), reverse=True)
    return sorted_list + ["Direct/Two"]

def get_top_combos():
    sorted_c = sorted(st.session_state.combo_counts.items(), key=lambda x: x[1], reverse=True)
    top_list = [x[0] for x in sorted_c[:8]]
    defaults = ["X5", "V5", "1", "2", "A", "B", "C", "P"]
    for d in defaults:
        if len(top_list) >= 8: break
        if d not in top_list: top_list.append(d)
    return top_list

# ==========================================
# 3. サイドバー: ロード機能
# ==========================================
with st.sidebar:
    st.header("💾 Save Data")
    if os.path.exists(SAVE_STATE_FILE):
        st.info("前回のデータが見つかりました")
        st.markdown('<div class="load-btn">', unsafe_allow_html=True)
        if st.button("📂 続きから再開 (Load Auto-save)"):
            load_autosave()
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.caption("保存されたデータはありません")

# ==========================================
# 4. アプリ進行フロー
# ==========================================

# --- 初期設定 ---
if st.session_state.stage < 6:
    st.title("🛠️ Game Setup")
    
    if st.session_state.stage == 0:
        st.subheader("Step 1: Set Number")
        val = st.text_input("Set", value="1")
        if st.button("Next"):
            st.session_state.set_name = val
            st.session_state.stage = 1
            auto_save()
            st.rerun()

    elif st.session_state.stage == 1:
        st.subheader("Step 2: Video URL")
        val = st.text_input("URL", value="")
        if st.button("Next"):
            st.session_state.video_url = val
            st.session_state.stage = 2
            auto_save()
            st.rerun()

    elif st.session_state.stage == 2:
        idx = st.session_state.roster_cursor
        pos_names = ["1 (Server)", "6 (Back-C)", "5 (Back-L)", "4 (Front-L)", "3 (Front-C)", "2 (Front-R)"]
        st.subheader(f"Step 3: Lineup ({idx+1}/6)")
        st.info(f"Position: **{pos_names[idx]}**")
        
        def roster_done():
            k = f"roster_{idx}"
            p_name = st.session_state[k]
            if p_name:
                st.session_state.temp_roster.append(p_name)
                if st.session_state.roster_cursor < 5:
                    st.session_state.roster_cursor += 1
                else:
                    st.session_state.stage = 3
            
        st.text_input("Player Name", key=f"roster_{idx}", on_change=roster_done)
        if st.button("Next (Button)"): pass 

    elif st.session_state.stage == 3:
        st.subheader("Step 4: Confirm")
        r = st.session_state.temp_roster
        st.markdown(f"""
        <div class="rot-grid">
            <div class="rot-cell rot-front">4: {r[3]}</div>
            <div class="rot-cell rot-front">3: {r[4]}</div>
            <div class="rot-cell rot-front">2: {r[5]}</div>
            <div class="rot-cell">5: {r[2]}</div>
            <div class="rot-cell">6: {r[1]}</div>
            <div class="rot-cell rot-server">1: {r[0]}</div>
        </div>""", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        if c1.button("OK"):
            st.session_state.rotation = st.session_state.temp_roster
            st.session_state.stage = 4
            auto_save()
            st.rerun()
        if c2.button("Retry"):
            st.session_state.stage = 2
            st.session_state.roster_cursor = 0
            st.session_state.temp_roster = []
            st.rerun()

    elif st.session_state.stage == 4:
        st.subheader("Step 5: Liberos")
        val = st.text_input("Names (comma separated)")
        if st.button("Next"):
            st.session_state.liberos = [x.strip() for x in val.split(',')] if val else []
            st.session_state.stage = 5
            auto_save()
            st.rerun()

    elif st.session_state.stage == 5:
        st.subheader("Step 6: First Phase")
        c1, c2 = st.columns(2)
        if c1.button("Serve (We)"):
            st.session_state.phase = 'S'; st.session_state.stage = 6; auto_save(); st.rerun()
        if c2.button("Reception (Op)"):
            st.session_state.phase = 'R'; st.session_state.stage = 6; auto_save(); st.rerun()

# ==========================================
# --- Stage 6: MAIN SCOUTING ---
# ==========================================
elif st.session_state.stage == 6:
    
    c_score, c_rot = st.columns([1.5, 1])
    with c_score:
        st.markdown(f'<div class="score-board">{st.session_state.score[0]}-{st.session_state.score[1]} ({st.session_state.phase})</div>', unsafe_allow_html=True)
        b1, b2 = st.columns(2)
        if b1.button("My Point (+1)"): update_score('my'); st.rerun()
        if b2.button("Op Point (+1)"): update_score('op'); st.rerun()

    with c_rot:
        r = st.session_state.rotation
        st.markdown(f"""
        <div class="rot-grid">
            <div class="rot-cell rot-front">{r[3]}</div>
            <div class="rot-cell rot-front">{r[4]}</div>
            <div class="rot-cell rot-front">{r[5]}</div>
            <div class="rot-cell">{r[2]}</div>
            <div class="rot-cell">{r[1]}</div>
            <div class="rot-cell rot-server">{r[0]}</div>
        </div>""", unsafe_allow_html=True)

    st.divider()

    col_map, col_card = st.columns([0.8, 1.5])
    
    # --- Map ---
    with col_map:
        st.markdown("**MAP**")
        court_img = create_court_img(st.session_state.points)
        val = streamlit_image_coordinates(
            court_img, 
            key=f"main_court_{st.session_state.key_map}", 
            width=230, height=460
        )
        if val:
            p = (val['x'], val['y'])
            if not st.session_state.points or st.session_state.points[-1] != p:
                if len(st.session_state.points) < 2:
                    st.session_state.points.append(p)
                    if len(st.session_state.points) == 2 and st.session_state.scout_step == 4:
                        st.session_state.scout_step = 5
                    st.rerun()
                else:
                    st.session_state.points = [p]
                    st.rerun()
        msg = "Start" if len(st.session_state.points)==0 else ("End" if len(st.session_state.points)==1 else "Done")
        st.caption(f"Tap: {msg}")

    # --- Input Card ---
    with col_card:
        st.markdown('<div class="input-card">', unsafe_allow_html=True)
        
        # Step 0: Time
        if st.session_state.scout_step == 0:
            st.markdown('<div class="step-header">1. Time</div>', unsafe_allow_html=True)
            disp_time = format_time(st.session_state.time_buffer)
            st.markdown(f"<h1 style='text-align:center; font-size:60px; margin:0;'>{disp_time}</h1>", unsafe_allow_html=True)
            
            k1, k2, k3 = st.columns(3)
            if k1.button(" 7 "): st.session_state.time_buffer += "7"; st.rerun()
            if k2.button(" 8 "): st.session_state.time_buffer += "8"; st.rerun()
            if k3.button(" 9 "): st.session_state.time_buffer += "9"; st.rerun()
            
            k4, k5, k6 = st.columns(3)
            if k4.button(" 4 "): st.session_state.time_buffer += "4"; st.rerun()
            if k5.button(" 5 "): st.session_state.time_buffer += "5"; st.rerun()
            if k6.button(" 6 "): st.session_state.time_buffer += "6"; st.rerun()
            
            k7, k8, k9 = st.columns(3)
            if k7.button(" 1 "): st.session_state.time_buffer += "1"; st.rerun()
            if k8.button(" 2 "): st.session_state.time_buffer += "2"; st.rerun()
            if k9.button(" 3 "): st.session_state.time_buffer += "3"; st.rerun()
            
            k0, kc, ke = st.columns(3)
            if k0.button(" 0 "): st.session_state.time_buffer += "0"; st.rerun()
            if kc.button(" CLR "): st.session_state.time_buffer = ""; st.rerun()
            if ke.button("ENTER", type="primary"):
                st.session_state.current_input_data['time'] = disp_time
                st.session_state.scout_step = 1
                st.rerun()

        # Step 1: Skill
        elif st.session_state.scout_step == 1:
            st.markdown('<div class="step-header">2. Skill</div>', unsafe_allow_html=True)
            cols = st.columns(3)
            skills = [("S", "Serve"), ("R", "Reception"), ("A", "Attack"), ("B", "Block"), ("D", "Dig"), ("E", "Set")]
            for i, (sk, label) in enumerate(skills):
                if cols[i%3].button(f"{sk}\n{label}"):
                    st.session_state.current_input_data['skill'] = sk
                    if sk == 'S': 
                        st.session_state.current_input_data['player'] = st.session_state.rotation[0]
                        st.session_state.current_input_data['setter'] = ""
                        st.session_state.current_input_data['combo'] = ""
                        st.session_state.scout_step = 4 
                    elif sk == 'A': st.session_state.scout_step = 2
                    else: st.session_state.scout_step = 2
                    st.rerun()
            if st.button("🔙 Back"): st.session_state.scout_step = 0; st.rerun()

        # Step 2: Player
        elif st.session_state.scout_step == 2:
            st.markdown('<div class="step-header">3. Player</div>', unsafe_allow_html=True)
            cols = st.columns(2)
            candidates = st.session_state.rotation + st.session_state.liberos
            for i, p in enumerate(candidates):
                if cols[i%2].button(p):
                    st.session_state.current_input_data['player'] = p
                    if st.session_state.current_input_data['skill'] == 'A': st.session_state.scout_step = 25
                    else: st.session_state.scout_step = 4
                    st.rerun()
            if st.button("🔙 Back"): st.session_state.scout_step = 1; st.rerun()

        # Step 2.5: Setter
        elif st.session_state.scout_step == 25:
            st.markdown('<div class="step-header">3.5 Setter</div>', unsafe_allow_html=True)
            setters = get_sorted_setters()
            cols = st.columns(2)
            for i, s in enumerate(setters):
                if cols[i%2].button(s):
                    st.session_state.current_input_data['setter'] = s
                    count_setter_usage(s)
                    st.session_state.scout_step = 3
                    st.rerun()
            if st.button("🔙 Back"): st.session_state.scout_step = 2; st.rerun()

        # Step 3: Combo
        elif st.session_state.scout_step == 3:
            st.markdown('<div class="step-header">3.8 Combo</div>', unsafe_allow_html=True)
            top_combos = get_top_combos()
            cc = st.columns(4)
            for i, c in enumerate(top_combos):
                if cc[i%4].button(c):
                    st.session_state.current_input_data['combo'] = c
                    st.session_state.scout_step = 4
                    st.rerun()
            st.markdown("---")
            c_val = st.text_input("Type new combo")
            if st.button("Add & Next"):
                if c_val:
                    st.session_state.current_input_data['combo'] = c_val
                    st.session_state.scout_step = 4
                    st.rerun()
            if st.button("🔙 Back"): st.session_state.scout_step = 25; st.rerun()

        # Step 4: Map Wait
        elif st.session_state.scout_step == 4:
            st.markdown('<div class="step-header">4. Map Input</div>', unsafe_allow_html=True)
            st.info("👈 左のコートを2回タップ")
            if st.button("Skip Map"): st.session_state.scout_step = 5; st.rerun()
            if st.button("🔙 Back"): 
                sk = st.session_state.current_input_data.get('skill')
                st.session_state.scout_step = 3 if sk == 'A' else (1 if sk == 'S' else 2)
                st.rerun()

        # Step 5: Quality
        elif st.session_state.scout_step == 5:
            st.markdown('<div class="step-header">5. Quality</div>', unsafe_allow_html=True)
            q1, q2 = st.columns(2)
            with q1:
                if st.button("# Perfect"): commit_record("#")
                if st.button("! OK"): commit_record("!")
                if st.button("/ Rebound"): commit_record("/")
            with q2:
                if st.button('" Good'): commit_record('"')
                if st.button("- Poor"): commit_record("-")
                if st.button("^ Error"): commit_record("^")
            if st.button("T BlockOut"): commit_record("T")
            st.markdown("---")
            if st.button("🔙 Back (Map)"):
                st.session_state.scout_step = 4
                st.session_state.points = []
                st.session_state.key_map += 1
                st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)
        if st.button("🔄 Reset Input"):
            st.session_state.scout_step = 0
            st.session_state.points = []
            st.rerun()

    # --- Data & Footer ---
    st.markdown("### Data Log")
    if len(st.session_state.data_log) > 0:
        df = pd.DataFrame(st.session_state.data_log)
        st.dataframe(df.iloc[::-1], height=150)
        
        c_sub, c_dl = st.columns(2)
        with c_sub:
            with st.expander("選手交代 / リベロ"):
                out_p = st.selectbox("OUT", st.session_state.rotation)
                in_p = st.text_input("IN Name")
                if st.button("Change"):
                    if in_p: 
                        idx = st.session_state.rotation.index(out_p)
                        st.session_state.rotation[idx] = in_p
                        auto_save()
                        st.rerun()
                lib_t = st.text_input("Liberos", ",".join(st.session_state.liberos))
                if st.button("Update"):
                    st.session_state.liberos = [x.strip() for x in lib_t.split(',')]
                    auto_save()
                    st.rerun()
        with c_dl:
            c_format, c_dbtn = st.columns(2)
            with c_format:
                file_format = st.radio("Format:", [".xlsx", ".csv"], horizontal=True)
            with c_dbtn:
                export_df = df.copy()
                export_df.rename(columns={"video_url": "Video_URL", "video_time": "Time_Sec"}, inplace=True)
                if file_format == ".xlsx":
                    buf = io.BytesIO()
                    with pd.ExcelWriter(buf, engine='xlsxwriter') as writer:
                        export_df.to_excel(writer, index=False)
                    st.download_button("📥 Download", buf.getvalue(), "scout.xlsx", "application/vnd.ms-excel")
                else:
                    csv = export_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button("📥 Download", csv, "scout.csv", "text/csv")
