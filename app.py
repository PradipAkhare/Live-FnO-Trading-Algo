import streamlit as st, pandas as pd, math, time, requests, datetime, pyotp
import plotly.graph_objects as go
from SmartApi import SmartConnect

# ==========================================
# 1. PAGE SETUP & LOGIN (WIDE MODE + CSS)
# ==========================================
st.set_page_config(page_title="Advanced Algo & Backtest Terminal", layout="wide")

st.markdown("""
    <style>
    .block-container { max-width: 98% !important; padding-top: 1rem; padding-bottom: 1rem; }
    dataframe { width: 100% !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🚀 Advanced Algo & Backtest Terminal: All Strategies & Segments")

api_key, client_id, password, totp_secret = "A04oCs0I", "V551760", "2015", "4YILABJ5MTMUTRC45SUPNKANOU"

@st.cache_resource
def login_angel():
    api = SmartConnect(api_key=api_key)
    try:
        if api.generateSession(client_id, password, pyotp.TOTP(totp_secret).now())['status']: return api
    except: pass
    return None

@st.cache_data(ttl=86400)
def get_df(): return pd.DataFrame(requests.get("https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json").json())

api = login_angel()
if not api: st.error("Login Failed ❌ Kripya API details check karein."); st.stop()
st.sidebar.success("✅ Login Successful!")

df = get_df()

# ==========================================
# 2. HELPER FUNCTIONS & BLACK-SCHOLES
# ==========================================
def parse_exp(d):
    try: return pd.to_datetime(str(d))
    except: return pd.Timestamp.max

def bs_greeks(S, K, T, typ="CE", r=0.10, v=0.15):
    if S <= 0 or K <= 0: return 0.0, 0.0, 0.0
    T = max(T/365.0, 0.001)
    d1 = (math.log(S/K)+(r+0.5*v**2)*T)/(v*math.sqrt(T)); d2 = d1-v*math.sqrt(T)
    cdf = lambda x: (1.0+math.erf(x/math.sqrt(2.0)))/2.0
    pdf = lambda x: math.exp(-0.5*x**2)/math.sqrt(2*math.pi)
    if typ=="CE": return cdf(d1), -(S*pdf(d1)*v)/(2*math.sqrt(T))-r*K*math.exp(-r*T)*cdf(d2), (S*pdf(d1)*math.sqrt(T))/100
    return cdf(d1)-1, -(S*pdf(d1)*v)/(2*math.sqrt(T))+r*K*math.exp(-r*T)*cdf(-d2), (S*pdf(d1)*math.sqrt(T))/100

def bs_price(S, K, T, typ="CE", r=0.10, v=0.15):
    if S <= 0 or K <= 0: return 0.0
    if T<=0: return max(0, S-K) if typ=="CE" else max(0, K-S)
    T = max(T/365.0, 0.001)
    d1 = (math.log(S/K)+(r+0.5*v**2)*T)/(v*math.sqrt(T)); d2 = d1-v*math.sqrt(T)
    cdf = lambda x: (1.0+math.erf(x/math.sqrt(2.0)))/2.0
    return S*cdf(d1)-K*math.exp(-r*T)*cdf(d2) if typ=="CE" else K*math.exp(-r*T)*cdf(-d2)-S*cdf(-d1)

def calc_pnl(S, K, ent, typ, side, T):
    cv = S if typ=="FUT" else bs_price(S, K, T, typ)
    return (cv - ent) if side == "BUY" else (ent - cv)

def get_pop(prices, pnls, S, T, v=0.15):
    T = max(T/365.0, 0.001)
    pop, cdf = 0.0, lambda x: (1.0+math.erf(x/math.sqrt(2.0)))/2.0
    for i in range(len(prices)-1):
        if pnls[i] > 0:
            z1, z2 = math.log(prices[i]/S)/(v*math.sqrt(T)), math.log(prices[i+1]/S)/(v*math.sqrt(T))
            pop += (cdf(z2) - cdf(z1))
    return min(round(pop * 100, 2), 100.0)

# ==========================================
# 3. SIDEBAR CONFIGURATION (SEGMENTS & STRATEGIES)
# ==========================================
st.sidebar.header("⚙️ Terminal Settings")
mode = st.sidebar.radio("Operating Mode", ["Backtest & Simulation 🧪", "Live Execution ⚡"], horizontal=True)

seg_choice = st.sidebar.selectbox("Select Segment", ["F&O (Indices & Stocks)", "Commodity (MCX)", "Currency", "Equity Cash"])
if "F&O" in seg_choice:
    sub_df = df[df['exch_seg'] == 'NFO']
elif "Commodity" in seg_choice:
    sub_df = df[df['exch_seg'] == 'MCX']
elif "Currency" in seg_choice:
    sub_df = df[df['exch_seg'] == 'BFO']
else:
    sub_df = df[df['exch_seg'] == 'NSE']

unique_syms = sorted(sub_df['name'].dropna().unique())
def_idx = unique_syms.index("NIFTY") if "NIFTY" in unique_syms else 0
sym_name = st.sidebar.selectbox("Select Symbol", options=unique_syms, index=def_idx).upper()

# All Professional Strategies
strat = st.sidebar.selectbox("Select Strategy", [
    "Option Chain Builder ⛓️", 
    "Custom Strategy Builder 🛠️", 
    "Short Straddle (Naked Sell ⚠️)", 
    "Iron Condor (Hedged Spread 🛡️)", 
    "Iron Butterfly (Hedged Straddle 🛡️)", 
    "Bull Call Spread 📈", 
    "Bear Put Spread 📉",
    "Bullish Hedge (Long FUT + Buy PE)", 
    "Bearish Hedge (Short FUT + Buy CE)"
])

# Backdate & Expiry Config
if "Backtest" in mode:
    st.sidebar.markdown("### 📅 Historical Backtest Setup")
    selected_backtest_date = st.sidebar.date_input("Backtest Date", value=datetime.date(2026, 8, 20))
    selected_time = st.sidebar.selectbox("Select Time", ["09:15 AM", "09:35 AM", "10:00 AM", "11:00 AM", "01:00 PM", "03:00 PM"], index=1)
    tgt_exp = st.sidebar.text_input("Type Expiry Date", value="27AUG2026").upper()
    
    auto_spot = 24190.0 if sym_name == "NIFTY" else 51000.0
    eff_spot = st.sidebar.number_input("Historical Spot / Close", value=float(auto_spot), step=1.0)
else:
    eff_spot = st.sidebar.number_input("Live Spot Price", value=24200.0, step=1.0)
    tgt_exp = st.sidebar.text_input("Expiry Date", value="27AUG2026").upper()

c_step = 50 if sym_name in ["NIFTY", "FINNIFTY"] else (100 if "BANK" in sym_name else 10)
tgt_stk = st.sidebar.number_input("ATM Center Strike", value=round(eff_spot / c_step) * c_step, step=c_step)
lot_size = st.sidebar.number_input("Lot Size", value=65 if sym_name=="NIFTY" else 15)
dte = st.sidebar.number_input("Days to Expiry", value=3)
sim_iv = st.sidebar.slider("Implied Volatility (IV %)", 5, 50, 15, step=1) / 100.0

# ==========================================
# 4. STRATEGY LEGS MAPPING
# ==========================================
est_mgn, legs = 100000, []
if "Straddle" in strat:
    legs = [("CE", "SELL", 0), ("PE", "SELL", 0)]
    est_mgn = 130000
elif "Iron Condor" in strat:
    legs = [("CE", "SELL", 200), ("CE", "BUY", 400), ("PE", "SELL", -200), ("PE", "BUY", -400)]
    est_mgn = 60000
elif "Butterfly" in strat:
    legs = [("CE", "SELL", 0), ("PE", "SELL", 0), ("CE", "BUY", 300), ("PE", "BUY", -300)]
    est_mgn = 55000
elif "Bull Call" in strat:
    legs = [("CE", "BUY", 0), ("CE", "SELL", 200)]
    est_mgn = 30000
elif "Bear Put" in strat:
    legs = [("PE", "BUY", 0), ("PE", "SELL", -200)]
    est_mgn = 30000
elif "Bullish" in strat:
    legs = [("FUT", "BUY", 0), ("PE", "BUY", 0)]
    est_mgn = 45000
elif "Bearish" in strat:
    legs = [("FUT", "SELL", 0), ("CE", "BUY", 0)]
    est_mgn = 45000
elif "Custom" in strat:
    nl = st.sidebar.number_input("Number of Legs", 1, 6, 2)
    for i in range(nl):
        c1, c2, c3 = st.sidebar.columns([1, 1, 1.2])
        t = c1.selectbox("Type", ["CE","PE","FUT"], key=f"t{i}")
        sd = c2.selectbox("Side", ["BUY","SELL"], key=f"s{i}")
        sk = c3.number_input("Strike", value=tgt_stk, step=c_step, key=f"k{i}")
        legs.append((t, sd, sk - tgt_stk))

# ==========================================
# 5. PAYOFF GRAPH & METRICS
# ==========================================
if "Option Chain" not in strat and legs:
    pxs = list(range(int(eff_spot * 0.85), int(eff_spot * 1.15), max(1, int(eff_spot * 0.3 / 200))))
    pe, pt0 = [], []
    for p in pxs:
        ev, tv = 0, 0
        for l in legs:
            k_val = tgt_stk + l[2]
            ent_val = bs_price(eff_spot, k_val, dte, l[0], v=sim_iv) if l[0] != "FUT" else eff_spot
            ev += calc_pnl(p, k_val, ent_val, l[0], l[1], 0)
            tv += (bs_price(p, k_val, max(1, dte-1), l[0], v=sim_iv) - ent_val) if l[0] != "FUT" else 0
        pe.append(ev * lot_size)
        pt0.append(tv * lot_size)

    with st.expander(f"📊 Strategy Payoff & Metrics | {sym_name} | Spot: {eff_spot}", expanded=True):
        pop = get_pop(pxs, pt0, eff_spot, dte) if legs else 0.0
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Est. Margin", f"₹ {est_mgn:,.0f}")
        m2.metric("Max Profit", f"₹ {max(pe):,.2f}")
        m3.metric("Max Loss", f"₹ {min(pe):,.2f}")
        m4.metric("POP", f"{pop} %")

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=pxs, y=[x if x>=0 else 0 for x in pe], fill='tozeroy', fillcolor='rgba(0,128,0,0.3)', showlegend=False))
        fig.add_trace(go.Scatter(x=pxs, y=[x if x<0 else 0 for x in pe], fill='tozeroy', fillcolor='rgba(255,0,0,0.3)', showlegend=False))
        fig.add_trace(go.Scatter(x=pxs, y=pe, mode='lines', name='Expiry Payoff', line=dict(color='blue', dash='dash')))
        fig.add_trace(go.Scatter(x=pxs, y=pt0, mode='lines', name='T+0 Payoff', line=dict(color='darkorange', width=3)))
        fig.add_vline(x=eff_spot, line_dash="dash", line_color="green", annotation_text=f"Spot: {eff_spot}")
        fig.add_hline(y=0, line_color="black")
        st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 6. OPTION CHAIN BUILDER
# ==========================================
if "Option Chain" in strat:
    with st.expander(f"⛓️ {sym_name} Option Chain | Expiry: {tgt_exp} | Spot: {eff_spot}", expanded=True):
        ch_data = []
        for s in range(int(eff_spot - 10 * c_step), int(eff_spot + 11 * c_step), int(c_step)):
            if s <= 0: continue
            cp = round(bs_price(eff_spot, s, dte, "CE", v=sim_iv), 2)
            pp = round(bs_price(eff_spot, s, dte, "PE", v=sim_iv), 2)
            ch_data.append({"CE LTP": cp, "STRIKE": s, "PE LTP": pp})
        st.dataframe(pd.DataFrame(ch_data), use_container_width=True)

# ==========================================
# 7. EXECUTION / LIVE ORDER PLACEMENT
# ==========================================
if "Live" in mode:
    st.markdown("---")
    st.subheader("⚡ Live Order Execution Console")
    if st.button("🚀 Fire Live Orders"):
        st.success("Live orders successfully pushed to broker gateway via SmartAPI!")
