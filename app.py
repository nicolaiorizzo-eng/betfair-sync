import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json, re, time, calendar
import numpy as np
import plotly.graph_objects as go

st.set_page_config(page_title="Betfair Trading Dashboard", page_icon="📈", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
  body { background:#f2f4f8; }

  .metric-card {
    background:#fff;
    border-radius:10px;
    padding:12px 8px;
    border:1px solid #e4e7ec;
    box-shadow:0 1px 4px rgba(0,0,0,0.06);
    height:84px;
    display:flex;
    flex-direction:column;
    justify-content:center;
    align-items:center;
    text-align:center;
  }
  .metric-label { font-size:10px; color:#999; font-weight:700; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:4px; }
  .metric-value { font-size:18px; font-weight:800; line-height:1.1; }
  .metric-sub   { font-size:10px; color:#bbb; margin-top:3px; }

  .card {
    background:#fff;
    border-radius:12px;
    padding:16px 18px 12px 18px;
    border:1px solid #e4e7ec;
    box-shadow:0 1px 6px rgba(0,0,0,0.07);
    margin-bottom:18px;
  }
  .card-title {
    font-size:11px;
    font-weight:800;
    color:#555;
    text-transform:uppercase;
    letter-spacing:0.6px;
    margin-bottom:12px;
    padding-bottom:8px;
    border-bottom:1px solid #f0f0f0;
  }

  .stat-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
  .stat-item { background:#f8f9fa; border-radius:8px; padding:10px 8px; text-align:center; }
  .stat-item-label { font-size:10px; color:#999; font-weight:600; text-transform:uppercase; margin-bottom:3px; }
  .stat-item-value { font-size:15px; font-weight:800; color:#1a1a2e; }

  .pos { color:#0F6E56; } .neg { color:#C0392B; } .neu { color:#1a1a2e; }

  /* Calendar day buttons */
  div[data-testid="stButton"] button {
    width:100% !important;
    border-radius:7px !important;
    min-height:56px !important;
    padding:4px 2px !important;
    font-size:11px !important;
    font-weight:800 !important;
    border:1.5px solid #eee !important;
    background:#fafafa !important;
    color:#ddd !important;
    box-shadow:none !important;
    line-height:1.3 !important;
  }
  .win-btn button {
    background:linear-gradient(135deg,#d4f5e9,#a8ead0) !important;
    border-color:#5fcca8 !important;
    color:#0F6E56 !important;
    box-shadow:0 2px 5px rgba(95,204,168,0.25) !important;
  }
  .win-btn button:hover {
    transform:translateY(-2px);
    box-shadow:0 4px 10px rgba(95,204,168,0.35) !important;
  }
  .loss-btn button {
    background:linear-gradient(135deg,#fde8e4,#f9c4bb) !important;
    border-color:#e8836c !important;
    color:#C0392B !important;
    box-shadow:0 2px 5px rgba(232,131,108,0.25) !important;
  }
  .loss-btn button:hover {
    transform:translateY(-2px);
    box-shadow:0 4px 10px rgba(232,131,108,0.35) !important;
  }
  .selected-btn button {
    outline:2.5px solid #1D9E75 !important;
    outline-offset:1px !important;
    box-shadow:0 4px 12px rgba(0,0,0,0.2) !important;
  }
  .selected-loss-btn button {
    outline:2.5px solid #C0392B !important;
    outline-offset:1px !important;
  }

  .bet-row { border-radius:7px; padding:8px 10px; margin-bottom:5px; font-size:12px; border-left:3px solid #ccc; }
  .bet-row.win  { background:#f0faf5; border-left-color:#0F6E56; }
  .bet-row.loss { background:#fdf0ee; border-left-color:#C0392B; }

  section[data-testid="stSidebar"] { background:#1a1a2e !important; }
  section[data-testid="stSidebar"] * { color:#eee !important; }
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
    fig.update_layout(height=height, margin=dict(l=0,r=0,t=4,b=0),
        plot_bgcolor='#ffffff', paper_bgcolor='#ffffff',
        xaxis=dict(showgrid=False,linecolor='#eee'),
        yaxis=dict(gridcolor='#f0f0f0',linecolor='#eee'))
    st.plotly_chart(fig, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

def metric_card(col, label, value, cls="neu", sub=""):
    sub_html=f'<div class="metric-sub">{sub}</div>' if sub else ''
    col.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value {cls}">{value}</div>{sub_html}</div>',unsafe_allow_html=True)

def stat_item(label, value, color="#1a1a2e"):
    return f'<div class="stat-item"><div class="stat-item-label">{label}</div><div class="stat-item-value" style="color:{color}">{value}</div></div>'

# ── sidebar ────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 Betfair Dashboard")
    st.markdown("---")
    uploaded=st.file_uploader("Upload ExchangeBets_Settled.csv", type="csv")
    if uploaded:
        raw_df=pd.read_csv(uploaded)
        st.success(f"✅ {len(raw_df)} rows loaded")
        if st.button("🔄 Sync to Google Sheets", use_container_width=True):
            with st.spinner("Syncing..."):
                sheet=connect_sheets()
                if sheet:
                    prc=process_csv(raw_df); added=sync_to_sheets(prc,sheet)
                    st.success(f"✅ {added} new bets synced!")
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
avg_roi     = (total_pnl / total_liab * 100) if total_liab > 0 else 0  # actual ROI = total P/L / total liability
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
metric_card(cols[1],"Strike Rate",     f"{strike_rate:.1f}%",     "pos" if strike_rate>=50 else "neg",f"{len(wins_df)}/{total_bets}")
metric_card(cols[2],"ROI",               f"{avg_roi:+.1f}%",         "pos" if avg_roi>=0 else "neg","P/L ÷ Liability")
metric_card(cols[3],"Total Liability", f"£{total_liab:.2f}",      "neu")
metric_card(cols[4],"Avg Liability",   f"£{avg_liab:.2f}",        "neu","per bet")
metric_card(cols[5],"Profit Days",     f"{profit_days}/{total_days}","pos" if profit_days>=total_days/2 else "neg")
metric_card(cols[6],"Best Day",        f"£{best_day:+.2f}",       "pos")
metric_card(cols[7],"Worst Day",       f"£{worst_day:+.2f}",      "pos" if worst_day>=0 else "neg")

st.markdown("<br>", unsafe_allow_html=True)

# ── advanced analytics ─────────────────────────────────────────────────────────
st.markdown("#### Advanced Analytics")
ac1,ac2,ac3=st.columns(3)
with ac1:
    st.markdown(f'''<div class="card"><div class="card-title">💰 Profitability Metrics</div>
      <div class="stat-grid">
        {stat_item("Largest Win",   f"+£{largest_win:.2f}",  "#0F6E56")}
        {stat_item("Largest Loss",  f"£{largest_loss:.2f}",  "#C0392B")}
        {stat_item("Profit Factor", f"{profit_factor:.2f}",  "#0F6E56" if profit_factor>=1 else "#C0392B")}
        {stat_item("EV per Bet",    f"£{ev_per_bet:+.2f}",   "#0F6E56" if ev_per_bet>=0 else "#C0392B")}
        {stat_item("Avg Odds",      f"{avg_odds:.2f}")}
        {stat_item("Total Bets",    str(total_bets))}
      </div></div>''',unsafe_allow_html=True)
with ac2:
    st.markdown(f'''<div class="card"><div class="card-title">📉 Risk Metrics</div>
      <div class="stat-grid">
        {stat_item("Max Drawdown",  f"£{max_dd:.2f}",        "#C0392B" if max_dd<0 else "#0F6E56")}
        {stat_item("Std Dev P/L",   f"£{std_pnl:.2f}")}
        {stat_item("Avg Liability", f"£{avg_liab:.2f}")}
        {stat_item("Win Streak",    str(max_win_streak),     "#0F6E56")}
        {stat_item("Loss Streak",   str(max_loss_streak),    "#C0392B")}
        {stat_item("Profit Days",   f"{profit_days}/{total_days}")}
      </div></div>''',unsafe_allow_html=True)
with ac3:
    st.markdown(f'''<div class="card"><div class="card-title">🎯 Win/Loss Breakdown</div>
      <div class="stat-grid">
        {stat_item("Avg Win",     f"+£{avg_win:.2f}",  "#0F6E56")}
        {stat_item("Avg Loss",    f"£{avg_loss:.2f}",  "#C0392B")}
        {stat_item("W/L Ratio",   f"{wl_ratio:.2f}",   "#0F6E56" if wl_ratio>=1 else "#C0392B")}
        {stat_item("Strike Rate", f"{strike_rate:.1f}%","#0F6E56" if strike_rate>=50 else "#C0392B")}
        {stat_item("Total Won",   f"+£{total_won:.2f}", "#0F6E56")}
        {stat_item("Total Lost",  f"-£{total_lost:.2f}","#C0392B")}
      </div></div>''',unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── cumulative + risk vs return ────────────────────────────────────────────────
r1c1,r1c2=st.columns(2)
with r1c1:
    cum=filtered.groupby('DateKey')['P/L'].sum().reset_index().sort_values('DateKey')
    cum['Cumulative']=cum['P/L'].cumsum(); cum['Date']=pd.to_datetime(cum['DateKey'])
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=cum['Date'],y=cum['Cumulative'],fill='tozeroy',
        line=dict(color='#1D9E75' if total_pnl>=0 else '#D85A30',width=2.5),
        fillcolor='rgba(29,158,117,0.12)' if total_pnl>=0 else 'rgba(216,90,48,0.12)',
        hovertemplate='%{x|%d %b}<br>Cumulative: £%{y:.2f}<extra></extra>'))
    fig.add_hline(y=0,line_dash="dash",line_color="#ddd",line_width=1)
    fig.update_layout(yaxis=dict(tickprefix='£'))
    plotly_card("📉 Cumulative P&L", fig, 260)
with r1c2:
    risk=pd.DataFrame({'Date':dliab.index,'Liability':dliab.values,'PnL':dpnl.reindex(dliab.index).values})
    fig2=go.Figure()
    fig2.add_trace(go.Bar(x=risk['Date'],y=risk['Liability'],name='Daily Liability',
        marker_color='rgba(100,140,255,0.25)',hovertemplate='%{x}<br>Liability: £%{y:.2f}<extra></extra>'))
    fig2.add_trace(go.Scatter(x=risk['Date'],y=risk['PnL'],name='Daily P/L',mode='lines+markers',
        line=dict(color='#1D9E75',width=2),
        marker=dict(color=['#1D9E75' if v>=0 else '#D85A30' for v in risk['PnL']],size=7),
        hovertemplate='%{x}<br>P&L: £%{y:.2f}<extra></extra>'))
    fig2.add_hline(y=0,line_dash="dash",line_color="#ddd",line_width=1)
    fig2.update_layout(yaxis=dict(tickprefix='£'),
        legend=dict(orientation='h',yanchor='bottom',y=1.02,xanchor='right',x=1))
    plotly_card("⚖️ Daily Risk vs Return", fig2, 260)

st.markdown("<br>", unsafe_allow_html=True)

# ── calendar + day detail ──────────────────────────────────────────────────────
if 'selected_day' not in st.session_state:
    st.session_state.selected_day = None

col_cal, col_detail = st.columns([3,2])

with col_cal:
    st.markdown('<div class="card"><div class="card-title">📅 P&L Calendar</div>', unsafe_allow_html=True)
    months_avail=sorted(filtered['Date'].dt.to_period('M').unique().astype(str),reverse=True)
    cal_month=st.selectbox("Month",options=months_avail,label_visibility="collapsed")
    cal_year,cal_mon=int(cal_month.split('-')[0]),int(cal_month.split('-')[1])
    mdata=filtered[(filtered['Date'].dt.year==cal_year)&(filtered['Date'].dt.month==cal_mon)]
    day_pnl_map  = mdata.groupby(mdata['Date'].dt.day)['P/L'].sum().to_dict()
    day_bets_map = mdata.groupby(mdata['Date'].dt.day)['BetID'].count().to_dict()

    # Calendar — clickable, styled via aria-label CSS selectors
    first_dow     = calendar.monthrange(cal_year, cal_mon)[0]
    days_in_month = calendar.monthrange(cal_year, cal_mon)[1]

    st.markdown(
        '<div style="display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-bottom:6px">' +
        ''.join([f'<div style="text-align:center;font-size:10px;font-weight:700;color:#bbb;text-transform:uppercase;padding:2px 0">{d}</div>'
                  for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']]) +
        '</div>', unsafe_allow_html=True)

    all_days = [None] * first_dow + list(range(1, days_in_month+1))
    while len(all_days) % 7 != 0:
        all_days.append(None)

    # Build per-button CSS using aria-label attribute selector
    css_parts = ["<style>"]
    for dn in range(1, days_in_month+1):
        pnl = day_pnl_map.get(dn, None)
        if pnl is None:
            continue
        dk     = f"{cal_year}-{str(cal_mon).zfill(2)}-{str(dn).zfill(2)}"
        is_sel = (st.session_state.selected_day == dk)
        bets   = day_bets_map.get(dn, 0)
        pstr   = f"{dn}\n{chr(43) if pnl>=0 else chr(45) if pnl<0 else chr(43)}{chr(163)}{abs(pnl):.0f}\n{bets}b"
        lbl    = pstr.replace("\n", "\\A ")
        bg     = ("linear-gradient(135deg,#a8ead0,#5fcca8)" if is_sel else "linear-gradient(135deg,#d4f5e9,#a8ead0)") if pnl>=0 else ("linear-gradient(135deg,#f9c4bb,#e8836c)" if is_sel else "linear-gradient(135deg,#fde8e4,#f9c4bb)")
        brd    = "#5fcca8" if pnl>=0 else "#e8836c"
        clr    = "#0F6E56" if pnl>=0 else "#C0392B"
        out    = f"outline:2.5px solid {clr};outline-offset:2px;" if is_sel else ""
        css_parts.append(f"""
          button[aria-label="{lbl}"] {{
            background:{bg} !important; border:1.5px solid {brd} !important;
            color:{clr} !important; font-weight:800 !important; font-size:12px !important;
            min-height:64px !important; border-radius:8px !important;
            white-space:pre-line !important; line-height:1.5 !important;
            box-shadow:0 2px 6px rgba(0,0,0,0.09) !important; {out}
          }}
          button[aria-label="{lbl}"]:hover {{
            transform:translateY(-2px) !important; box-shadow:0 5px 14px rgba(0,0,0,0.16) !important;
          }}""")
    css_parts.append("</style>")
    st.markdown("".join(css_parts), unsafe_allow_html=True)

    for row_start in range(0, len(all_days), 7):
        row  = all_days[row_start:row_start+7]
        cols = st.columns(7)
        for ci, dn in enumerate(row):
            with cols[ci]:
                if dn is None:
                    st.markdown('<div style="min-height:66px;border:1px solid #f0f0f0;border-radius:8px;background:#fafafa;margin:2px 0"></div>', unsafe_allow_html=True)
                else:
                    pnl  = day_pnl_map.get(dn, None)
                    bets = day_bets_map.get(dn, 0)
                    dk   = f"{cal_year}-{str(cal_mon).zfill(2)}-{str(dn).zfill(2)}"
                    if pnl is not None:
                        sign = chr(43) if pnl>=0 else chr(45) if pnl<0 else chr(43)
                        pstr = f"{dn}\n{sign}{chr(163)}{abs(pnl):.0f}\n{bets}b"
                        if st.button(pstr, key=f"cal_{dk}", use_container_width=True):
                            st.session_state.selected_day = dk if st.session_state.selected_day != dk else None
                            st.rerun()
                    else:
                        st.markdown(f'<div style="min-height:66px;border:1px solid #eee;border-radius:8px;background:#fafafa;display:flex;align-items:flex-start;padding:6px;margin:2px 0"><span style="font-size:11px;color:#ddd;font-weight:600">{dn}</span></div>', unsafe_allow_html=True)

    days_with_data = sorted(day_pnl_map.keys())
    st.markdown('</div>', unsafe_allow_html=True)

with col_detail:
    # Auto-select last day with data in current month if nothing selected
    if days_with_data:
        default_dk = f"{cal_year}-{str(cal_mon).zfill(2)}-{str(max(days_with_data)).zfill(2)}"
        if st.session_state.selected_day is None or st.session_state.selected_day not in [f"{cal_year}-{str(cal_mon).zfill(2)}-{str(d).zfill(2)}" for d in days_with_data]:
            st.session_state.selected_day = default_dk

    st.markdown('<div class="card"><div class="card-title">📋 Day Analysis</div>', unsafe_allow_html=True)
    if st.session_state.selected_day:
        pts = st.session_state.selected_day.split('-')
        sel_date = datetime(int(pts[0]), int(pts[1]), int(pts[2]))
        ddf = filtered[filtered['Date'].dt.date == sel_date.date()]
        if not ddf.empty:
            dt=ddf['P/L'].sum(); dl=ddf['Liability'].sum()
            dw=(ddf['Outcome']=='WIN').sum(); db=len(ddf)
            droi=(dt/dl*100) if dl>0 else 0
            dc="#0F6E56" if dt>=0 else "#C0392B"
            st.markdown(f'''<div style="background:#f8f9fa;border-radius:8px;padding:14px;margin-bottom:10px;border:1px solid #eee">
              <div style="font-size:11px;color:#aaa;font-weight:700;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:4px">{sel_date.strftime('%A, %d %B %Y')}</div>
              <div style="font-size:28px;font-weight:800;color:{dc};margin-bottom:10px">{'+'if dt>=0 else ''}£{dt:.2f}</div>
              <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px">
                <div style="text-align:center;background:#fff;border-radius:8px;padding:8px;border:1px solid #eee">
                  <div style="font-size:9px;color:#aaa;font-weight:700;text-transform:uppercase">Bets</div>
                  <div style="font-weight:800;font-size:18px;color:#222">{db}</div>
                </div>
                <div style="text-align:center;background:#fff;border-radius:8px;padding:8px;border:1px solid #eee">
                  <div style="font-size:9px;color:#aaa;font-weight:700;text-transform:uppercase">Wins</div>
                  <div style="font-weight:800;font-size:18px;color:#222">{dw}/{db}</div>
                </div>
                <div style="text-align:center;background:#fff;border-radius:8px;padding:8px;border:1px solid #eee">
                  <div style="font-size:9px;color:#aaa;font-weight:700;text-transform:uppercase">ROI</div>
                  <div style="font-weight:800;font-size:18px;color:{dc}">{droi:+.1f}%</div>
                </div>
              </div>
            </div>''', unsafe_allow_html=True)
            for _, bet in ddf.iterrows():
                pc  = "#0F6E56" if bet['P/L']>=0 else "#C0392B"
                bg  = "#f0faf5" if bet['P/L']>=0 else "#fdf0ee"
                brd = "#0F6E56" if bet['P/L']>=0 else "#C0392B"
                st.markdown(f'''<div style="background:{bg};border-left:3px solid {brd};border-radius:7px;
                  padding:9px 11px;margin-bottom:6px">
                  <div style="font-weight:700;font-size:12px;color:#222">{bet["Event"]}</div>
                  <div style="color:#888;font-size:11px;margin-top:2px">{bet["Market"]} · {bet["Selection"]} · {bet["Type"]} @ {bet["Avg Odds"]:.2f}</div>
                  <div style="display:flex;justify-content:space-between;margin-top:5px;align-items:center">
                    <span style="font-size:11px;color:#bbb">Liability: £{bet["Liability"]:.2f}</span>
                    <span style="font-weight:800;font-size:13px;color:{pc}">{"+"if bet["P/L"]>=0 else ""}£{bet["P/L"]:.2f}</span>
                  </div>
                </div>''', unsafe_allow_html=True)
        else:
            st.info("No bets found for this date.")
    else:
        st.markdown('''<div style="text-align:center;padding:60px 20px;color:#ccc">
          <div style="font-size:40px;margin-bottom:10px">📅</div>
          <div style="font-size:13px;font-weight:500">Select a day from the calendar<br>to see a full breakdown</div>
        </div>''', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── market + day of week ───────────────────────────────────────────────────────
r3c1,r3c2=st.columns(2)
with r3c1:
    ms=filtered.groupby('Market').agg(PnL=('P/L','sum'),Bets=('BetID','count')).reset_index().sort_values('PnL')
    fig3=go.Figure(go.Bar(x=ms['PnL'],y=ms['Market'],orientation='h',
        marker_color=['#1D9E75' if v>=0 else '#D85A30' for v in ms['PnL']],
        hovertemplate='<b>%{y}</b><br>P&L: £%{x:.2f}<extra></extra>'))
    fig3.update_layout(yaxis=dict(showgrid=False),xaxis=dict(tickprefix='£'))
    plotly_card("🏷️ P&L by Market Type", fig3, 270)

with r3c2:
    # normalize to midnight so Monday bets aren't excluded by time-of-day
    today=datetime.now().replace(hour=0,minute=0,second=0,microsecond=0)
    ws=today-timedelta(days=today.weekday())
    we=ws+timedelta(days=7)
    tw=filtered[(filtered['Date']>=ws)&(filtered['Date']<we)]
    dow_order=['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    if not tw.empty:
        dp=tw.groupby('DayOfWeek')['P/L'].sum().reindex(dow_order).fillna(0)
        wt=tw['P/L'].sum()
        cap=f"Week {ws.strftime('%d %b')} – {(we-timedelta(days=1)).strftime('%d %b %Y')} · Total: {'+'if wt>=0 else ''}£{wt:.2f}"
    else:
        dp=filtered.groupby('DayOfWeek')['P/L'].sum().reindex(dow_order).fillna(0)
        cap="No bets this week — showing all-time by day of week"
    fig4=go.Figure(go.Bar(x=dp.index,y=dp.values,
        marker_color=['#1D9E75' if v>=0 else '#D85A30' for v in dp.values],
        hovertemplate='%{x}<br>P&L: £%{y:.2f}<extra></extra>'))
    fig4.add_hline(y=0,line_dash="dash",line_color="#ddd",line_width=1)
    fig4.update_layout(xaxis=dict(showgrid=False),yaxis=dict(tickprefix='£'))
    plotly_card("📆 P&L by Day of Week — This Week", fig4, 260)
    st.caption(cap)

st.markdown("<br>", unsafe_allow_html=True)

# ── all bets table ─────────────────────────────────────────────────────────────
st.markdown('<div class="card"><div class="card-title">📋 All Bets</div>', unsafe_allow_html=True)
tdf=filtered[['DateStr','Event','Market','Selection','Type','Avg Odds','Liability','P/L','ROI','Outcome']].copy()
tdf=tdf.sort_values('DateStr',ascending=False)
tdf['Liability']=tdf['Liability'].apply(lambda x:f"£{x:.2f}")
tdf['P/L']=tdf['P/L'].apply(lambda x:f"+£{x:.2f}" if x>=0 else f"-£{abs(x):.2f}")
tdf['ROI']=tdf['ROI'].apply(lambda x:f"{x:+.1f}%")
tdf.columns=['Date','Event','Market','Selection','Type','Odds','Liability','P/L','ROI','Outcome']
st.dataframe(tdf,use_container_width=True,hide_index=True)
st.markdown('</div>', unsafe_allow_html=True)
