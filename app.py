import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json, re, time, calendar
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Betfair Trading Dashboard", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

# ── BETFAIR ORIGINAL HIGH-CONTRAST THEME STYLING ──
st.markdown("""
<style>
  /* Main app container background */
  .stApp { background-color: #0a111c !important; color: #f2f6fc !important; }
  body { background-color: #0a111c; color: #f2f6fc; }

  /* Metric cards top summary */
  .metric-card {
    background: #111b29;
    border-radius: 8px;
    padding: 12px 8px;
    border: 1px solid #1a2a3e;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    height: 84px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    text-align: center;
  }
  .metric-label { font-size: 10px; color: #7e8e9f; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .metric-value { font-size: 18px; font-weight: 800; line-height: 1.1; }
  .metric-sub   { font-size: 10px; color: #526375; margin-top: 3px; }

  /* Main platform layout cards */
  .card {
    background: #111b29;
    border-radius: 10px;
    padding: 16px 18px 12px 18px;
    border: 1px solid #1a2a3e;
    box-shadow: 0 10px 20px rgba(0,0,0,0.4);
    margin-bottom: 18px;
  }
  .card-title {
    font-size: 11px;
    font-weight: 800;
    color: #ffb800; 
    text-transform: uppercase;
    letter-spacing: 0.6px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #1a2a3e;
  }

  .stat-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 8px; }
  .stat-item { background: #0b121d; border-radius: 6px; padding: 10px 8px; text-align: center; border: 1px solid #1a2a3e; }
  .stat-item-label { font-size: 10px; color: #7e8e9f; font-weight: 600; text-transform: uppercase; margin-bottom: 3px; }
  .stat-item-value { font-size: 15px; font-weight: 800; color: #f2f6fc; }

  /* P&L Performance Colors */
  .pos { color: #2bf0a2 !important; } 
  .neg { color: #ff5252 !important; } 
  .neu { color: #f2f6fc !important; }

  /* Left navigation sidebar panel */
  section[data-testid="stSidebar"] { background: #070c14 !important; border-right: 1px solid #1a2a3e; }
  section[data-testid="stSidebar"] * { color: #cbd5e1 !important; }

  /* Settled trade rows */
  .bet-row { border-radius: 6px; padding: 8px 10px; margin-bottom: 5px; font-size: 12px; border-left: 3px solid #334155; }
  .bet-row.win  { background: #0c251c; border-left-color: #2bf0a2; }
  .bet-row.loss { background: #2e1418; border-left-color: #ff5252; }

  /* ── SOLID CALENDAR BACKGROUND FORCE OVERRIDES ── */
  button[aria-label*="🟢"], button[aria-label*="🔴"], button[aria-label*="⚪"] {
    min-height: 85px !important; 
    height: 85px !important;
    border-radius: 8px !important; 
    padding: 6px 10px !important; 
    width: 100% !important;
    transition: transform 0.1s ease, box-shadow 0.1s ease !important;
    display: block !important;
  }

  /* Internal text structures */
  button[aria-label*="🟢"] div[data-testid="stMarkdownContainer"] p,
  button[aria-label*="🔴"] div[data-testid="stMarkdownContainer"] p,
  button[aria-label*="⚪"] div[data-testid="stMarkdownContainer"] p {
    display: flex !important;
    flex-direction: column !important;
    height: 100% !important;
    width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    text-align: center !important;
    font-size: 14px !important;
    font-weight: 800 !important;
    line-height: 1.3 !important;
  }

  /* Force top-left execution on the day number string segment */
  button[aria-label*="🟢"] div[data-testid="stMarkdownContainer"] p::first-line,
  button[aria-label*="🔴"] div[data-testid="stMarkdownContainer"] p::first-line,
  button[aria-label*="⚪"] div[data-testid="stMarkdownContainer"] p::first-line {
    font-size: 11px !important;
    font-weight: 700 !important;
    color: #62778e !important;
    float: left !important;
    text-align: left !important;
    display: block !important;
    width: 100% !important;
  }

  /* Force Green Profile Background (Active Profit) */
  button[aria-label*="🟢"] {
    background-color: #0c251c !important;
    background: linear-gradient(135deg, #0f291f, #07140f) !important;
    border: 1.5px solid #1ba872 !important;
    color: #2bf0a2 !important;
  }
  button[aria-label*="🟢"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(43, 240, 162, 0.25) !important;
  }

  /* Force Red Profile Background (Active Loss) */
  button[aria-label*="🔴"] {
    background-color: #2e1418 !important;
    background: linear-gradient(135deg, #2a1216, #16080a) !important;
    border: 1.5px solid #cc3341 !important;
    color: #ff5252 !important;
  }
  button[aria-label*="🔴"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(255, 82, 82, 0.25) !important;
  }

  /* Force Graphite Slate Background (Empty Days) */
  button[aria-label*="⚪"] {
    background-color: #0b121d !important;
    background: #0b121d !important;
    border: 1.5px solid #1a2a3e !important;
    color: #3b4e63 !important;
  }
  button[aria-label*="⚪"]:hover {
    transform: translateY(-2px) !important;
    border-color: #2d435f !important;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.4) !important;
  }

  /* Active Container Selection Ring Override */
  button[aria-label*="🟢"][data-testid="baseButton-primary"],
  button[aria-label*="🔴"][data-testid="baseButton-primary"],
  button[aria-label*="⚪"][data-testid="baseButton-primary"] {
    border: 2px solid #ffb800 !important;
    outline: 2px solid #ffb800 !important;
    outline-offset: 1px !important;
    box-shadow: 0 0 12px rgba(255, 184, 0, 0.5) !important;
    transform: translateY(-1px) !important;
  }
</style>
""", unsafe_allow_html=True)

FILTER_FROM = datetime(2026, 6, 1)

# ── helpers ────────────────────────────────────────────────────────────────────
def safe_float(val, fallback=0.0):
    s = str(val).strip().replace('£','').replace(',','').replace('%','')
    if s in ("--","-","","nan"): return fallback
    try: return float(s)
    except: return fallback

def parse_date(raw):
    raw = str(raw).split(' ')[0].strip()
    if not raw or raw=='nan': return None
    for fmt in ('%d-%b-%y','%d/%m/%Y','%m/%d/%Y','%d-%b-%Y'):
        try: return datetime.strptime(raw, fmt)
        except: continue
    return None

def parse_description(desc):
    desc = str(desc)
    m = re.search(r'Betfair Bet ID \d+:(\d+)', desc)
    bet_id = m.group(1) if m else ""
    main = desc.split(" | Betfair")[0].strip()
    if "-" in main:
        parts=main.rsplit("-",1); left=parts[0].strip(); market=parts[1].strip()
    else:
        left=main; market=""
    selection=home_team=away_team=""
    event_name=left
    vm=re.search(r'\sv\s', left)
    if vm:
        home_team=left[:vm.start()].strip(); away_part=left[vm.end():]
        if market=="Match Odds":
            words=away_part.split()
            for i in range(len(words),0,-1):
                cand=" ".join(words[:i]); rem=" ".join(words[i:]).strip()
                if rem and not rem[0].islower(): away_team=cand; selection=rem; break
            if not away_team: away_team=away_part.strip()
        else:
            away_team=away_part
            for kw in [' Over ',' Under ',' Both Teams ',' Yes',' No']:
                if kw in away_part:
                    away_team=away_part[:away_part.index(kw)].strip()
                    selection=away_part[away_part.index(kw):].strip(); break
            away_team=away_team.strip()
        event_name=f"{home_team} v {away_team}"
    return event_name, home_team, away_team, market, selection, bet_id

def process_csv(df):
    rows=[]
    for _,row in df.iterrows():
        ev,ht,at,mk,sl,bid=parse_description(row.get('Description',''))
        d=parse_date(row.get('Settled',''))
        if d is None or not bid or d<FILTER_FROM: continue
        stake=safe_float(row.get('Stake (£)',0)); liab=safe_float(row.get('Liability (£)',0))
        pnl=safe_float(row.get('Profit/Loss',0)); odds=safe_float(row.get('Odds',0))
        btype=str(row.get('Type','N/A')); status=str(row.get('Status','')).lower()
        outcome='WIN' if status=='won' else 'LOSS'
        if liab==0 and stake>0: liab=stake
        roi=(pnl/liab*100) if liab>0 else 0.0
        rows.append({'Date':d,'DateStr':d.strftime('%d-%b-%Y'),'DateKey':d.strftime('%Y-%m-%d'),
                     'DayOfWeek':d.strftime('%A'),'Home Team':ht,'Away Team':at,'Event':ev,
                     'Market':mk,'Selection':sl,'Type':btype,'Avg Odds':odds,
                     'Liability':liab,'P/L':pnl,'ROI':roi,'Outcome':outcome,'BetID':bid})
    return pd.DataFrame(rows)

def connect_sheets():
    try:
        creds_dict=json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
        scope=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
        creds=Credentials.from_service_account_info(creds_dict,scopes=scope)
        client=gspread.authorize(creds)
        return client.open(st.secrets["GOOGLE_SHEET_NAME"]).sheet1
    except Exception as e:
        st.error(f"Sheets error: {e}"); return None

def sync_to_sheets(pdf, sheet):
    headers=sheet.row_values(1)
    if 'BetID' not in headers: st.error("Missing BetID column!"); return 0
    existing={str(r.get('BetID','')) for r in sheet.get_all_records() if r.get('BetID')}
    new_rows=[]
    for _,row in pdf.iterrows():
        if str(row['BetID']) in existing: continue
        new_rows.append([row['DateStr'],row['Home Team'],row['Away Team'],row['Event'],row['Market'],
                         row['Selection'],row['Type'],f"{row['Avg Odds']:.2f}",f"£{row['Liability']:.2f}",
                         f"£{row['P/L']:.2f}",f"{row['ROI']:.2f}%",row['Outcome'],row['BetID']])
        existing.add(str(row['BetID']))
    for i in range(0,len(new_rows),50):
        sheet.append_rows(new_rows[i:i+50],value_input_option='USER_ENTERED')
        if i+50<len(new_rows): time.sleep(2)
    return len(new_rows)

def compute_streaks(outcomes):
    max_win=max_loss=cur_win=cur_loss=0
    for o in outcomes:
        if o=='WIN': cur_win+=1; cur_loss=0
        else: cur_loss+=1; cur_win=0
        max_win=max(max_win,cur_win); max_loss=max(max_loss,cur_loss)
    return max_win, max_loss

def compute_max_drawdown(pnl_series):
    cumulative=pnl_series.cumsum()
    peak=cumulative.cummax()
    return (cumulative-peak).min()

def plotly_card(title, fig, height=270):
    st.markdown(f'<div class="card"><div class="card-title">{title}</div>', unsafe_allow_html=True)
    fig.update_layout(height=height, margin=dict(l=0,r=0,t=4,b=0), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#cbd5e1'), xaxis=dict(showgrid=False,linecolor='#1a2a3e'), yaxis=dict(gridcolor='#1a2a3e',linecolor='#1a2a3e'))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

def metric_card(col, label, value, cls="neu", sub=""):
    sub_html = f'<div class="metric-sub">{sub}</div>' if sub else ''
    col.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value {cls}">{value}</div>{sub_html}</div>', unsafe_allow_html=True)

def stat_item(label, value, color="#f2f6fc"):
    return f'<div class="stat-item"><div class="stat-item-label">{label}</div><div class="stat-item-value" style="color:{color}">{value}</div></div>'

# ── sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 Betfair Dashboard")
    st.markdown("---")
    uploaded=st.file_uploader("Upload ExchangeBets_Settled.csv", type="csv")
    if uploaded:
        raw_df=pd.read_csv(uploaded)
        st.success(f"Loaded {len(raw_df)} rows successfully")
        if st.button("🔄 Sync to Google Sheets", use_container_width=True):
            with st.spinner("Syncing data tracks..."):
                sheet=connect_sheets()
                if sheet:
                    prc=process_csv(raw_df); added=sync_to_sheets(prc,sheet)
                    st.success(f"Synced rows: {added}")
    st.markdown("---")
    st.markdown("### Filters")
    if uploaded:
        processed_df=process_csv(raw_df)
        if not processed_df.empty:
            mn=processed_df['Date'].min().date(); mx=processed_df['Date'].max().date()
            date_range=st.date_input("Date range",value=(mn,mx),min_value=mn,max_value=mx)
            mf=st.multiselect("Market type",options=sorted(processed_df['Market'].unique()),default=list(processed_df['Market'].unique()))
            bf=st.multiselect("Bet type",options=sorted(processed_df['Type'].unique()),default=list(processed_df['Type'].unique()))

# ── main ───────────────────────────────────────────────────────────────────────
st.title("📈 Betfair Trading Dashboard")
if not uploaded:
    st.info("👈 Upload your ExchangeBets_Settled.csv from the sidebar to get started.")
    st.stop()
if processed_df.empty:
    st.warning("No data found from June 2026 onwards."); st.stop()

if len(date_range)==2:
    s,e=date_range
    filtered=processed_df[(processed_df['Date'].dt.date>=s)&(processed_df['Date'].dt.date<=e)]
else:
    filtered=processed_df
filtered=filtered[filtered['Market'].isin(mf)]
filtered=filtered[filtered['Type'].isin(bf)]
if filtered.empty: st.warning("No data matches your filters."); st.stop()

# ── stats ──────────────────────────────────────────────────────────────────────
total_bets  = len(filtered)
total_liab  = filtered['Liability'].sum()
total_pnl   = filtered['P/L'].sum()
avg_roi     = (total_pnl / total_liab * 100) if total_liab > 0 else 0 
wins_df     = filtered[filtered['Outcome']=='WIN']
losses_df   = filtered[filtered['Outcome']=='LOSS']
strike_rate = len(wins_df)/total_bets*100 if total_bets>0 else 0
avg_odds    = filtered['Avg Odds'].mean()
largest_win = filtered['P/L'].max()
largest_loss= filtered['P/L'].min()
total_won   = wins_df['P/L'].sum()
total_lost  = abs(losses_df['P/L'].sum())
profit_factor=total_won/total_lost if total_lost>0 else float('inf')
ev_per_bet  = total_pnl/total_bets if total_bets>0 else 0
max_dd      = compute_max_drawdown(filtered.sort_values('Date')['P/L'])
max_win_streak,max_loss_streak=compute_streaks(filtered.sort_values('Date')['Outcome'].tolist())
avg_win     = wins_df['P/L'].mean() if len(wins_df)>0 else 0
avg_loss    = losses_df['P/L'].mean() if len(losses_df)>0 else 0
wl_ratio    = abs(avg_win/avg_loss) if avg_loss!=0 else float('inf')
std_pnl     = filtered['P/L'].std()
dpnl        = filtered.groupby('DateKey')['P/L'].sum()
dliab       = filtered.groupby('DateKey')['Liability'].sum()
profit_days = (dpnl>0).sum(); total_days=len(dpnl)
best_day    = dpnl.max(); worst_day=dpnl.min()
avg_liab    = filtered['Liability'].mean()

# ── metric cards ───────────────────────────────────────────────────────────────
st.markdown("#### Performance Overview")
cols=st.columns(8)
metric_card(cols[0],"Total P&L",       f"£{total_pnl:+.2f}",     "pos" if total_pnl>=0 else "neg")
metric_card(cols[1],"Strike Rate",     f"{strike_rate:.1f}%",     "pos" if strike_rate>=50 else "neg",f"{len(wins_df)}/{total_bets
