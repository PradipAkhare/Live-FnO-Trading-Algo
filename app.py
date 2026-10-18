import streamlit as st, pandas as pd, math, time, requests, datetime, pyotp
import plotly.graph_objects as go
from SmartApi import SmartConnect

# ==========================================
# 1. PAGE SETUP & LOGIN (WIDE MODE + CSS)
# ==========================================
st.set_page_config(page_title="Opstra Clone - Option Chain & Payoff Terminal", layout="wide")

st.markdown("""
    <style>
    .block-container { max-width: 98% !important; padding-top: 1rem; padding-bottom: 1rem; }
    dataframe { width: 100% !important; }
    </style>
""", unsafe_allow_html=True)

st.title("🚀 Opstra Clone: Option Chain Builder, Strategies & Payoff Graph")

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
fno_df = df[df['exch_seg'].isin(['NFO', 'MCX', 'BFO'])]
unique_syms = sorted(fno_df['name'].dropna().unique())
def_idx = unique_syms.index("NIFTY") if "NIFTY" in unique_syms else 0

# ==========================================
# 2. HELPER FUNCTIONS & BLACK-SCHOLES
# ==========================================
def parse_exp(d):
    try: return pd.to_datetime(str(d))
    except: return pd.Timestamp.max

def get_token(sym, stk, typ, exp):
    if typ == "FUT": 
        f = fno_df[(fno_df['name']==sym) & (fno_df['symbol'].str.endswith('FUT'))].copy()
        if f.empty: return 99999, f"{sym}{exp}FUT", "NFO"
        f['exp_date'] = f['expiry'].apply(parse_exp)
        v_futs = f[f['exp_date'] >= parse_exp(exp)].sort_values('exp_date')
        f_tgt = v_futs if not v_futs.empty else f.sort_values('exp_date')
        return f_tgt.iloc[0]['token'], f_tgt.iloc[0]['symbol'], f_tgt.iloc[0]['exch_seg']
    else:
        f = fno_df[(fno_df['name']==sym) & (fno_df['expiry']==exp) & (fno_df['symbol'].str.endswith(typ))].copy()
        if f.empty:
            return 99999, f"{sym}{exp}{typ}", "NFO"
        f['num_stk'] = pd.to_numeric(f['strike'], errors='coerce')
        f['diff'] = f['num_stk'].apply(lambda x: min(abs(x-float(stk)), abs((x/100)-float(stk)), abs((x/10000)-float(stk))))
        f = f.sort_values('diff')
        return f.iloc[0]['token'], f.iloc[0]['symbol'], f.iloc[0]['exch_seg']

def safe_ltp(exch, sym, tok):
    try:
        res = api.ltpData(exch, sym, tok)
        if res and 'data' in res and 'ltp' in res['data']:
            return float(res['data']['ltp'])
    except: pass
    return 100.0

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
# 3. SIDEBAR CONFIGURATION
# ==========================================
st.sidebar.header("⚙️ Strategy & Symbol Settings")

strat = st.sidebar.selectbox("Select Strategy", [
    "Option Chain Builder ⛓️", 
    "Custom Strategy Builder 🛠️", 
    "Short Straddle (Naked Sell ⚠️)", 
    "Iron Butterfly (Hedged Straddle 🛡️)", 
    "Bullish Hedge (Long FUT + Buy PE)", 
    "Bearish Hedge (Short FUT + Buy CE)"
])

sym_name = st.sidebar.selectbox("Search F&O Symbol", options=unique_syms, index=def_idx).upper()

sym_df = fno_df[fno_df['name']==sym_name]
all_exps = []
if not sym_df.empty:
    opt_df = sym_df[sym_df['symbol'].str.endswith('CE') | sym_df['symbol'].str.endswith('PE')]
    if not opt_df.empty:
        all_exps = sorted(opt_df['expiry'].dropna().unique(), key=parse_exp)
        near_df = opt_df[opt_df['expiry']==all_exps[0]]
        c_lot = int(near_df.iloc[0]['lotsize'])
        seg = near_df.iloc[0]['exch_seg']
        raw_stks = sorted(near_df['strike'].astype(float).unique())
        stks = sorted(list(set([s/10000 if seg=='BFO' else (s/100 if seg=='NFO' else s) for s in raw_stks])))
        c_step = int(stks[1]-stks[0]) if len(stks)>1 else 50
        c_stk = int(stks[len(stks)//2])
    else:
        all_exps = sorted(sym_df['expiry'].dropna().unique(), key=parse_exp)
        c_lot, c_step, c_stk = int(sym_df.iloc[0]['lotsize']), 50, 25000
else: all_exps, c_lot, c_step, c_stk = ["29DEC2026"], 25, 50, 25000

sm_stks = {"NIFTY":24000, "BANKNIFTY":51000, "FINNIFTY":23000, "SENSEX":80000, "BANKEX":60000, "CRUDEOIL":6000, "GOLD":75000, "RELIANCE":3000}
if sym_name in sm_stks: c_stk = sm_stks[sym_name]

tgt_exp = st.sidebar.text_input("Type Expiry Date", value="27AUG2026").upper()
eff_spot = st.sidebar.number_input("Spot Price", value=float(c_stk), step=1.0)
tgt_stk = st.sidebar.number_input("ATM Center Strike", value=round(eff_spot / c_step) * c_step, step=c_step)
lot_size = st.sidebar.number_input("Lot Size", value=c_lot)
dte = st.sidebar.number_input("Days to Expiry", value=3)
sim_iv = st.sidebar.slider("Implied Volatility (IV %)", 5, 50, 15, step=1) / 100.0

# ==========================================
# 4. STRATEGY LEGS MAPPING
# ==========================================
est_mgn, legs = 100000, []
if "Straddle" in strat:
    legs = [("CE", "SELL", 0), ("PE", "SELL", 0)]
    est_mgn = 130000
elif "Butterfly" in strat:
    legs = [("CE", "SELL", 0), ("PE", "SELL", 0), ("CE", "BUY", 300), ("PE", "BUY", -300)]
    est_mgn = 55000
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
ld, aok = [], True
if "Option Chain" not in strat and legs:
    for t, sd, off in legs:
        tk, sm, ex = get_token(sym_name, tgt_stk + off, t, tgt_exp)
        if tk: ld.append({"t":t, "s":sd, "k":tgt_stk + off, "tk":tk, "sm":sm})

    if ld:
        pxs = list(range(int(eff_spot * 0.85), int(eff_spot * 1.15), max(1, int(eff_spot * 0.3 / 200))))
        pe, pt0 = [], []
        for p in pxs:
            ev, tv = 0, 0
            for l in ld:
                ent_val = bs_price(eff_spot, l['k'], dte, l['t'], v=sim_iv) if l['t'] != "FUT" else eff_spot
                ev += calc_pnl(p, l['k'], ent_val, l['t'], l['s'], 0)
                tv += (bs_price(p, l['k'], max(1, dte-1), l['t'], v=sim_iv) - ent_val) if l['t'] != "FUT" else 0
            pe.append(ev * lot_size)
            pt0.append(tv * lot_size)

        with st.expander(f"📊 Strategy Payoff & Metrics | {sym_name} | Spot: {eff_spot}", expanded=True):
            pop = get_pop(pxs, pt0, eff_spot, dte) if ld else 0.0
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
            ch_data.append({"Buy CE": False, "Sell CE": False, "CE LTP": cp, "STRIKE": s, "PE LTP": pp, "Buy PE": False, "Sell PE": False})
        
        df_ch = pd.DataFrame(ch_data)
        ed_ch = st.data_editor(df_ch, hide_index=True, use_container_width=True)
        for _, r in ed_ch.iterrows():
            off = int(r['STRIKE']) - tgt_stk
            if r['Buy CE']: legs.append(("CE", "BUY", off))
            if r['Sell CE']: legs.append(("CE", "SELL", off))
            if r['Buy PE']: legs.append(("PE", "BUY", off))
            if r['Sell PE']: legs.append(("PE", "SELL", off))
