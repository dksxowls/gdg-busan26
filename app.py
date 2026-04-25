import streamlit as st
import json
import requests
import random

# ─────────────────────────────────────────────
# 설정 (보안을 위해 st.secrets 사용)
# ─────────────────────────────────────────────
# 깃허브에 키를 직접 적지 않고, 배포 환경의 금고(Secrets)에서 가져옵니다.
try:
    GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
except KeyError:
    st.error("Secrets 설정에서 'GEMINI_API_KEY'를 찾을 수 없습니다. 설정을 확인해 주세요.")
    st.stop()

st.set_page_config(page_title="🧠 딴생각 AI", layout="wide")

# ─────────────────────────────────────────────
# CSS (디자인 유지)
# ─────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background-color: #b2c7d9; }

  .bubble-wrap { display:flex; margin:6px 12px; align-items:flex-end; gap:8px; }
  .bubble-wrap.user { flex-direction:row-reverse; }
  .bubble {
    max-width:65%; padding:10px 14px; border-radius:18px;
    font-size:14px; line-height:1.6; word-break:break-word; white-space:pre-wrap;
  }
  .bubble.user  { background:#fee500; border-bottom-right-radius:4px; color:#000; }
  .bubble.ai    { background:#ffffff; border-bottom-left-radius:4px;  color:#000; }
  .bubble.bleed {
    background:#fff3e0; border-bottom-left-radius:4px; color:#7c4e00;
    border-left:3px solid #ff9800; font-style:italic;
  }

  .daydream-panel {
    margin:4px 12px 10px 50px;
    background:linear-gradient(135deg,#f3e8ff,#ede0ff);
    border:1px dashed #b08ee0; border-radius:12px;
    padding:10px 14px;
    font-size:13px; color:#5a3d8a; font-style:italic;
  }
  .daydream-panel .dptitle {
    font-size:11px; font-weight:bold; color:#9b6ee0;
    margin-bottom:6px; font-style:normal; letter-spacing:.5px;
  }
  .thought-flow {
    font-size:11px; color:#8e6bbf; margin:2px 0 4px 50px;
    font-family:monospace; opacity:.85;
  }
  .bleed-notice {
    font-size:11px; color:#e65100; margin:2px 0 6px 50px; font-style:italic;
  }

  .label { font-size:11px; color:#555; margin-bottom:3px; }
  .label.ai   { text-align:left;  margin-left:42px; }
  .label.user { text-align:right; margin-right:12px; }
  .avatar {
    width:36px; height:36px; border-radius:50%;
    background:#7c5cbf; color:white;
    display:flex; align-items:center; justify-content:center;
    font-size:18px; flex-shrink:0;
  }

  .distract-badge {
    display:inline-block; padding:2px 8px; border-radius:10px;
    font-size:11px; font-weight:bold;
  }
  .date-divider {
    text-align:center; color:#666; font-size:12px; margin:14px 0;
  }
  .date-divider::before,.date-divider::after {
    content:""; display:inline-block; width:28%; height:1px;
    background:#aaa; vertical-align:middle; margin:0 8px;
  }

  .status-card {
    border-radius:12px; padding:12px 16px; text-align:center;
    font-size:15px; font-weight:bold; margin-top:4px;
  }

  div[data-testid="stChatInput"]  { background:#fff; border-top:1px solid #ccc; }
  section[data-testid="stSidebar"]{ background:#1e1e2e; }
  section[data-testid="stSidebar"] * { color:white !important; }
</style>
""", unsafe_allow_html=True)

DAYDREAM_PROB = {1:0.40, 2:0.50, 3:0.60, 4:0.75, 5:0.90}
BLEED_PROB    = {1:0.00, 2:0.05, 3:0.10, 4:0.40, 5:0.80}

STATUS_INFO = {
    1: ("🙂", "정상",        "#1EB92A", "#2e7d32"),
    2: ("😟", "살짝 머리 아픔", "#ffc400", "#f57f17"),
    3: ("🤕", "조금 아프다",   "#ff7300", "#e65100"),
    4: ("🤯", "마니 아프다",   "#df054eb8", "#c62828"),
    5: ("🤪", "헤헤헿ㅎㅎ",   "#ff0000", "#6a1b9a"),
}

defaults = {
    "messages": [],
    "distract_level": 3,
    "cumulative_distract": 0,
    "pending_daydream_topic": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

with st.sidebar:
    st.markdown("## 🧠 AI의 딴생각 설정")
    st.markdown("---")
    level = st.slider("🎚️ 딴생각 강도", 1, 5, st.session_state.distract_level)
    st.session_state.distract_level = level
    dp = int(DAYDREAM_PROB[level] * 100)
    bp = int(BLEED_PROB[level] * 100)
    st.markdown(f"- 딴생각 발생: **{dp}%**")
    st.markdown(f"- 대화 침투: **{bp}%**")
    st.markdown("---")
    emoji, txt, bg, fg = STATUS_INFO[level]
    st.markdown(
        f'<div class="status-card" style="background:{bg};color:{fg};">'
        f'{emoji} AI 상태: {txt}</div>',
        unsafe_allow_html=True
    )
    st.markdown("---")
    if st.button("🗑️ 대화 초기화"):
        st.session_state.messages = []
        st.session_state.cumulative_distract = 0
        st.session_state.pending_daydream_topic = None
        st.rerun()

NORMAL_SYSTEM = """당신은 친근하고 유능한 AI 챗봇입니다.
사용자의 질문에 자연스럽고 도움이 되는 한국어로 답변하세요.
반드시 아래 JSON만 출력하세요 (마크다운 없이):
{"answer": "...", "thought_flow": ["..."], "dream_text": "...", "distract_score": 1}"""

DAYDREAM_SYSTEM = """당신은 친근하고 유능하지만 지금 살짝 딴생각 중인 AI입니다.
반드시 아래 JSON만 출력하세요:
{"answer": "...", "thought_flow": ["..."], "dream_text": "...", "distract_score": 3, "daydream_topic": "..."}"""

BLEED_SYSTEM = """당신은 AI인데 지금 딴생각이 대화에 새어나오고 있습니다.
반드시 아래 JSON만 출력하세요:
{"answer": "...", "thought_flow": ["..."], "dream_text": "...", "distract_score": 5, "daydream_topic": "...", "bleed": true}"""

def get_system(mode):
    return {"normal": NORMAL_SYSTEM, "daydream": DAYDREAM_SYSTEM, "bleed": BLEED_SYSTEM}[mode]

def call_gemini(user_prompt, history, mode):
    # 모델명은 최신 안정 버전을 권장합니다.
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}")

    gemini_history = []
    for m in history[-10:]:
        role = "user" if m["role"] == "user" else "model"
        text = m["content"] if m["role"] == "user" else m.get("answer", "")
        gemini_history.append({"role": role, "parts": [{"text": text}]})
    gemini_history.append({"role": "user", "parts": [{"text": user_prompt}]})

    payload = {
        "contents": gemini_history,
        "system_instruction": {"parts": [{"text": get_system(mode)}]},
        "generationConfig": {"temperature": 1.1, "response_mime_type": "application/json"}
    }
    err = {"answer":"오류가 발생했습니다.","thought_flow":["에러"],"dream_text":"회로가 꼬인 것 같아요...","distract_score":1}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            text = resp.json()['candidates'][0]['content']['parts'][0]['text']
            data = json.loads(text)
            return data
        else:
            st.error(f"API 오류: {resp.status_code}")
            return err
    except Exception as e:
        st.error(f"연결 오류: {e}")
        return err

st.markdown("""
<div style="background:#7c5cbf;padding:14px 20px;border-radius:0 0 12px 12px;
            display:flex;align-items:center;gap:12px;margin-bottom:10px;">
  <span style="font-size:28px">🧠</span>
  <div>
    <div style="color:white;font-weight:bold;font-size:16px">딴생각 AI</div>
    <div style="color:#d4b8ff;font-size:12px">Gemini 1.5 Flash Powered</div>
  </div>
</div>
""", unsafe_allow_html=True)

if not st.session_state.messages:
    st.markdown('<div class="date-divider">대화를 시작해보세요</div>', unsafe_allow_html=True)

for i, msg in enumerate(st.session_state.messages):
    if msg["role"] == "user":
        st.markdown(f'<div class="label user">나</div><div class="bubble-wrap user"><div class="bubble user">{msg["content"]}</div></div>', unsafe_allow_html=True)
    else:
        answer = msg.get("answer", "")
        has_dream = msg.get("has_dream", False)
        bubble_class = "bleed" if msg.get("bleed") else "ai"
        st.markdown(f'<div class="label ai">🧠 AI</div><div class="bubble-wrap"><div class="avatar">🤖</div><div class="bubble {bubble_class}">{answer}</div></div>', unsafe_allow_html=True)
        if has_dream:
            flow_str = " ➜ ".join(msg.get("thought_flow", []))
            st.markdown(f'<div class="thought-flow">💭 {flow_str}</div><div class="daydream-panel"><div class="dptitle">🌀 딴생각</div>{msg.get("dream_text")}</div>', unsafe_allow_html=True)

if prompt := st.chat_input("메시지를 입력하세요..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    lv = st.session_state.distract_level
    r = random.random()
    if r < DAYDREAM_PROB[lv] * BLEED_PROB[lv]: mode, has_dream = "bleed", True
    elif r < DAYDREAM_PROB[lv]: mode, has_dream = "daydream", True
    else: mode, has_dream = "normal", False
    
    with st.spinner("생각 중..."):
        res = call_gemini(prompt, st.session_state.messages[:-1], mode)
    res["has_dream"], res["role"] = has_dream, "ai"
    st.session_state.messages.append(res)
    st.rerun()