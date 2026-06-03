import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
import re
import time
import plotly.graph_objects as go
import plotly.express as px
import calendar

# ─── PAGE CONFIG ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Betfair Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── STYLING ───────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .metric-card {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 16px 20px;
    border: 1px solid #eee;
    text-align: center;
  }
  .metric-label { font-size: 13px; color: #666; margin-bottom: 4px; }
  .metric-value { font-size: 26px; font-weight: 700; }
  .pos { color: #0F6E56; }
  .neg { color: #C0392B; }
  .cal-day {
    border-radius: 6px;
    padding: 6px;
    text-align: center;
    font-size: 12px;
    min-height: 54px;
  }
  section[data-testid="stSidebar"] { background: #1a1a2e; }
  section[data-testid="stSidebar"] * { color: #eee !important; }
  h1, h2, h3 { font-weight: 700; }
</style>
""", unsafe_allow_html=True)

FILTER_FROM = datetime(2026, 6, 1)

# ─── HELPERS ───────────────────────────────────────────────────────────────────
def safe_float(val, fallback=0.0):
    s = str(val).strip().replace('£','').replace(',','').replace('%','')
    if s in ("--", "-", "", "nan"): return fallback
    try: return float(s)
    except: return fallback

def parse_date(raw):
    raw = str(raw).split(' ')[0].strip()
    if not raw or raw == 'nan': return None
    for fmt in ('%d-%b-%y', '%d/%m/%Y', '%m/%d/%Y', '%d-%b-%Y'):
        try: return datetime.strptime(raw, fmt)
        except: continue
    return None

def parse_description(desc):
    desc = str(desc)
    bet_id_match = re.search(r'Betfair Bet ID \d+:(\d+)', desc)
    bet_id = bet_id_match.group(1) if bet_id_match else ""
    main = desc.split(" | Betfair")[0].strip()
    if "-" in main:
        parts  = main.rsplit("-", 1)
        left   = parts[0].strip()
        market = parts[1].strip()
    else:
        left   = main
        market = ""
    selection = ""
    event_name = left
    home_team = ""
    away_team = ""
    v_match = re.search(r'\sv\s', left)
    if v_match:
        home_team = left[:v_match.start()].strip()
        away_part = left[v_match.end():]
        if market == "Match Odds":
            words = away_part.split()
            for i in range(len(words), 0, -1):
                candidate = " ".join(words[:i])
                remaining = " ".join(words[i:]).strip()
                if remaining and not remaining[0].islower():
                    away_team = candidate
                    selection = remaining
                    break
            if not away_team: away_team = away_part.strip()
        else:
            away_team = away_part
            for kw in [' Over ', ' Under ', ' Both Teams ', ' Yes', ' No']:
                if kw in away_part:
                    away_team = away_part[:away_part.index(kw)].strip()
                    selection = away_part[away_part.index(kw):].strip()
                    break
            away_team = away_team.strip()
        event_name = f"{home_team} v {away_team}"
    return event_name, home_team, away_team, market, selection, bet_id

def process_csv(df):
    rows = []
    for _, row in df.iterrows():
        event_name, home_team, away_team, market, selection, bet_id = parse_description(row.get('Description',''))
        parsed_date = parse_date(row.get('Settled', ''))
        if parsed_date is None or not bet_id: continue
        if parsed_date < FILTER_FROM: continue
        stake     = safe_float(row.get('Stake (£)', 0))
        liability = safe_float(row.get('Liability (£)', 0))
        pnl       = safe_float(row.get('Profit/Loss', 0))
        odds      = safe_float(row.get('Odds', 0))
        bet_type  = str(row.get('Type', 'N/A'))
        status    = str(row.get('Status', '')).lower()
        outcome   = 'WIN' if status == 'won' else 'LOSS'
        if liability == 0 and stake > 0: liability = stake
        roi = (pnl / liability * 100) if liability > 0 else 0.0
        rows.append({
            'Date': parsed_date,
            'DateStr': parsed_date.strftime('%d-%b-%Y'),
            'DayOfWeek': parsed_date.strftime('%A'),
            'Home Team': home_team,
            'Away Team': away_team,
            'Event': event_name,
            'Market': market,
            'Selection': selection,
            'Type': bet_type,
            'Avg Odds': odds,
            'Liability': liability,
            'P/L': pnl,
            'ROI': roi,
            'Outcome': outcome,
            'BetID': bet_id
        })
    return pd.DataFrame(rows)

def connect_sheets():
    try:
        creds_dict = json.loads(st.secrets["GOOGLE_CREDENTIALS_JSON"])
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds  = Credentials.from_service_account_info(creds_dict, scopes=scope)
        client = gspread.authorize(creds)
        sheet  = client.open(st.secrets["GOOGLE_SHEET_NAME"]).sheet1
        return sheet
    except Exception as e:
        st.error(f"Google Sheets connection failed: {e}")
        return None

def sync_to_sheets(processed_df, sheet):
    headers = sheet.row_values(1)
    if 'BetID' not in headers:
        st.error("Missing BetID column in sheet header row!")
        return 0
    existing = sheet.get_all_records()
    existing_ids = {str(r.get('BetID','')) for r in existing if r.get('BetID')}
    new_rows = []
    for _, row in processed_df.iterrows():
        if str(row['BetID']) in existing_ids: continue
        new_rows.append([
            row['DateStr'], row['Home Team'], row['Away Team'], row['Event'],
            row['Market'], row['Selection'], row['Type'],
            f"{row['Avg Odds']:.2f}", f"£{row['Liability']:.2f}",
            f"£{row['P/L']:.2f}", f"{row['ROI']:.2f}%", row['Outcome'], row['BetID']
        ])
        existing_ids.add(str(row['BetID']))
    if new_rows:
        for i in range(0, len(new_rows), 50):
            sheet.append_rows(new_rows[i:i+50], value_input_option='USER_ENTERED')
            if i + 50 < len(new_rows): time.sleep(2)
    return len(new_rows)

# ─── SIDEBAR ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📈 Betfair Dashboard")
    st.markdown("---")
    uploaded = st.file_uploader("Upload ExchangeBets_Settled.csv", type="csv")
    if uploaded:
        raw_df = pd.read_csv(uploaded)
        st.success(f"✅ {len(raw_df)} rows loaded")
        if st.button("🔄 Sync to Google Sheets", use_container_width=True):
            with st.spinner("Connecting to Google Sheets..."):
                sheet = connect_sheets()
                if sheet:
                    processed = process_csv(raw_df)
                    added = sync_to_sheets(processed, sheet)
                    st.success(f"✅ {added} new bets synced!")
    st.markdown("---")
    st.markdown("### Filters")
    if uploaded:
        processed_df = process_csv(raw_df)
        if not processed_df.empty:
            min_date = processed_df['Date'].min().date()
            max_date = processed_df['Date'].max().date()
            date_range = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
            market_filter = st.multiselect("Market type", options=sorted(processed_df['Market'].unique()), default=list(processed_df['Market'].unique()))
            bet_type_filter = st.multiselect("Bet type", options=sorted(processed_df['Type'].unique()), default=list(processed_df['Type'].unique()))

# ─── MAIN ──────────────────────────────────────────────────────────────────────
st.title("📈 Betfair Trading Dashboard")

if not uploaded:
    st.info("👈 Upload your ExchangeBets_Settled.csv from the sidebar to get started.")
    st.stop()

if processed_df.empty:
    st.warning("No data found from June 2026 onwards in this file.")
    st.stop()

# Apply filters
if len(date_range) == 2:
    start, end = date_range
    mask = (processed_df['Date'].dt.date >= start) & (processed_df['Date'].dt.date <= end)
    filtered = processed_df[mask]
else:
    filtered = processed_df

filtered = filtered[filtered['Market'].isin(market_filter)]
filtered = filtered[filtered['Type'].isin(bet_type_filter)]

if filtered.empty:
    st.warning("No data matches your filters.")
    st.stop()

# ─── METRIC CARDS ──────────────────────────────────────────────────────────────
total_pnl   = filtered['P/L'].sum()
total_bets  = len(filtered)
total_wins  = (filtered['Outcome'] == 'WIN').sum()
win_rate    = (total_wins / total_bets * 100) if total_bets > 0 else 0
total_liab  = filtered['Liability'].sum()
total_roi   = (total_pnl / total_liab * 100) if total_liab > 0 else 0
profit_days = filtered.groupby('Date')['P/L'].sum()
best_day    = profit_days.max()
worst_day   = profit_days.min()

c1, c2, c3, c4, c5, c6 = st.columns(6)
def card(col, label, value, cls=""):
    col.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value {cls}">{value}</div></div>', unsafe_allow_html=True)

card(c1, "Total P&L",    f"{'+'if total_pnl>=0 else ''}£{total_pnl:.2f}", "pos" if total_pnl>=0 else "neg")
card(c2, "Total Bets",   str(total_bets))
card(c3, "Win Rate",     f"{win_rate:.1f}%")
card(c4, "ROI",          f"{'+'if total_roi>=0 else ''}{total_roi:.1f}%", "pos" if total_roi>=0 else "neg")
card(c5, "Best Day",     f"+£{best_day:.2f}", "pos")
card(c6, "Worst Day",    f"-£{abs(worst_day):.2f}", "neg")

st.markdown("<br>", unsafe_allow_html=True)

# ─── CUMULATIVE P&L + CALENDAR ─────────────────────────────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    st.subheader("📉 Cumulative P&L")
    daily_pnl = filtered.groupby('Date')['P/L'].sum().reset_index().sort_values('Date')
    daily_pnl['Cumulative'] = daily_pnl['P/L'].cumsum()
    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=daily_pnl['Date'], y=daily_pnl['Cumulative'],
        fill='tozeroy',
        line=dict(color='#1D9E75', width=2),
        fillcolor='rgba(29,158,117,0.1)',
        hovertemplate='%{x|%d %b %Y}<br>Cumulative: £%{y:.2f}<extra></extra>'
    ))
    fig_cum.update_layout(
        height=280, margin=dict(l=0,r=0,t=10,b=0),
        xaxis=dict(showgrid=False),
        yaxis=dict(tickprefix='£', gridcolor='#f0f0f0'),
        plot_bgcolor='white', paper_bgcolor='white'
    )
    st.plotly_chart(fig_cum, use_container_width=True)

with col_right:
    st.subheader("📅 P&L Calendar")
    cal_month = st.selectbox("Month", options=sorted(filtered['Date'].dt.to_period('M').unique().astype(str), reverse=True), label_visibility="collapsed")
    cal_year, cal_mon = int(cal_month.split('-')[0]), int(cal_month.split('-')[1])
    month_data = filtered[(filtered['Date'].dt.year==cal_year) & (filtered['Date'].dt.month==cal_mon)]
    day_pnl = month_data.groupby(filtered['Date'].dt.day)['P/L'].sum()

    days_header = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    header_html = ''.join([f'<th style="text-align:center;font-size:11px;color:#999;padding:4px">{d}</th>' for d in days_header])

    first_dow = calendar.monthrange(cal_year, cal_mon)[0]
    days_in_month = calendar.monthrange(cal_year, cal_mon)[1]
    cells = ['<td></td>'] * first_dow
    for d in range(1, days_in_month+1):
        pnl = day_pnl.get(d, None)
        if pnl is not None:
            bg = '#E1F5EE' if pnl > 0 else '#FAECE7'
            border = '#9FE1CB' if pnl > 0 else '#F5C4B3'
            color = '#0F6E56' if pnl > 0 else '#C0392B'
            pnl_str = f"{'+'if pnl>=0 else ''}£{abs(pnl):.0f}"
            cell = f'<td style="padding:2px"><div style="background:{bg};border:1px solid {border};border-radius:6px;padding:4px;text-align:center;min-height:46px"><div style="font-size:11px;color:#999">{d}</div><div style="font-size:12px;font-weight:600;color:{color}">{pnl_str}</div></div></td>'
        else:
            cell = f'<td style="padding:2px"><div style="border:1px solid #eee;border-radius:6px;padding:4px;text-align:center;min-height:46px"><div style="font-size:11px;color:#ddd">{d}</div></div></td>'
        cells.append(cell)

    while len(cells) % 7 != 0:
        cells.append('<td></td>')

    rows_html = ''
    for i in range(0, len(cells), 7):
        rows_html += '<tr>' + ''.join(cells[i:i+7]) + '</tr>'

    st.markdown(f'<table style="width:100%;border-collapse:separate;border-spacing:0"><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>', unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─── MARKET + DAY OF WEEK ──────────────────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.subheader("🏷️ P&L by Market Type")
    market_pnl = filtered.groupby('Market')['P/L'].sum().reset_index().sort_values('P/L')
    fig_market = go.Figure(go.Bar(
        x=market_pnl['P/L'], y=market_pnl['Market'],
        orientation='h',
        marker_color=['#1D9E75' if v>=0 else '#D85A30' for v in market_pnl['P/L']],
        hovertemplate='%{y}<br>P&L: £%{x:.2f}<extra></extra>'
    ))
    fig_market.update_layout(
        height=300, margin=dict(l=0,r=0,t=10,b=0),
        xaxis=dict(tickprefix='£', gridcolor='#f0f0f0'),
        yaxis=dict(showgrid=False),
        plot_bgcolor='white', paper_bgcolor='white'
    )
    st.plotly_chart(fig_market, use_container_width=True)

with col_b:
    st.subheader("📆 P&L by Day of Week")
    dow_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    dow_pnl = filtered.groupby('DayOfWeek')['P/L'].sum().reindex(dow_order).fillna(0).reset_index()
    fig_dow = go.Figure(go.Bar(
        x=dow_pnl['DayOfWeek'], y=dow_pnl['P/L'],
        marker_color=['#1D9E75' if v>=0 else '#D85A30' for v in dow_pnl['P/L']],
        hovertemplate='%{x}<br>P&L: £%{y:.2f}<extra></extra>'
    ))
    fig_dow.update_layout(
        height=300, margin=dict(l=0,r=0,t=10,b=0),
        xaxis=dict(showgrid=False),
        yaxis=dict(tickprefix='£', gridcolor='#f0f0f0'),
        plot_bgcolor='white', paper_bgcolor='white'
    )
    st.plotly_chart(fig_dow, use_container_width=True)

# ─── RECENT BETS TABLE ─────────────────────────────────────────────────────────
st.subheader("📋 Recent Bets")
display_df = filtered[['DateStr','Event','Market','Selection','Type','Avg Odds','Liability','P/L','Outcome']].copy()
display_df = display_df.sort_values('DateStr', ascending=False).head(50)
display_df['Liability'] = display_df['Liability'].apply(lambda x: f"£{x:.2f}")
display_df['P/L'] = display_df['P/L'].apply(lambda x: f"+£{x:.2f}" if x>=0 else f"-£{abs(x):.2f}")
display_df.columns = ['Date','Event','Market','Selection','Type','Odds','Liability','P/L','Outcome']
st.dataframe(display_df, use_container_width=True, hide_index=True)
