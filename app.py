import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import json
import re
import time
import plotly.graph_objects as go
import calendar

st.set_page_config(
    page_title="Betfair Trading Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
  .metric-card {
    background: #f8f9fa;
    border-radius: 10px;
    padding: 16px 20px;
    border: 1px solid #eee;
    text-align: center;
  }
  .metric-label { font-size: 12px; color: #888; margin-bottom: 4px; font-weight: 500; }
  .metric-value { font-size: 22px; font-weight: 700; }
  .metric-sub { font-size: 11px; color: #aaa; margin-top: 2px; }
  .pos { color: #0F6E56; }
  .neg { color: #C0392B; }
  .neu { color: #333; }
  .section-title { font-size: 15px; font-weight: 700; margin-bottom: 8px; color: #222; }
  .day-bet-row { padding: 8px 10px; border-radius: 6px; margin-bottom: 6px; border: 1px solid #eee; font-size: 13px; }
  section[data-testid="stSidebar"] { background: #1a1a2e; }
  section[data-testid="stSidebar"] * { color: #eee !important; }
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
            'DateKey': parsed_date.strftime('%Y-%m-%d'),
            'DayOfWeek': parsed_date.strftime('%A'),
            'WeekStart': (parsed_date - timedelta(days=parsed_date.weekday())).strftime('%Y-%m-%d'),
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
        st.error("Missing BetID column in sheet!")
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
            with st.spinner("Syncing..."):
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
    st.warning("No data found from June 2026 onwards.")
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

# ─── METRICS ROW 1 ─────────────────────────────────────────────────────────────
total_pnl   = filtered['P/L'].sum()
total_bets  = len(filtered)
total_wins  = (filtered['Outcome'] == 'WIN').sum()
win_rate    = (total_wins / total_bets * 100) if total_bets > 0 else 0
total_liab  = filtered['Liability'].sum()
total_roi   = (total_pnl / total_liab * 100) if total_liab > 0 else 0
avg_liability = filtered['Liability'].mean()
daily_pnl_series = filtered.groupby('DateKey')['P/L'].sum()
daily_liab_series = filtered.groupby('DateKey')['Liability'].sum()
profit_days = (daily_pnl_series > 0).sum()
total_days  = len(daily_pnl_series)
best_day    = daily_pnl_series.max()
worst_day   = daily_pnl_series.min()
avg_odds    = filtered['Avg Odds'].mean()

# Sharpe-like consistency score (std dev of daily P/L — lower is more consistent)
daily_std = daily_pnl_series.std()

def card(col, label, value, cls="neu", sub=""):
    sub_html = f'<div class="metric-sub">{sub}</div>' if sub else ''
    col.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value {cls}">{value}</div>{sub_html}</div>', unsafe_allow_html=True)

c1,c2,c3,c4,c5,c6,c7,c8 = st.columns(8)
card(c1, "Total P&L",         f"£{total_pnl:+.2f}",       "pos" if total_pnl>=0 else "neg")
card(c2, "Win Rate",          f"{win_rate:.1f}%",          "pos" if win_rate>=50 else "neg", f"{total_wins}/{total_bets} bets")
card(c3, "ROI",               f"{total_roi:+.1f}%",        "pos" if total_roi>=0 else "neg")
card(c4, "Avg Liability",     f"£{avg_liability:.2f}",     "neu", "per bet")
card(c5, "Avg Odds",          f"{avg_odds:.2f}",           "neu", "per bet")
card(c6, "Profit Days",       f"{profit_days}/{total_days}","pos" if profit_days >= total_days/2 else "neg")
card(c7, "Best Day",          f"+£{best_day:.2f}",         "pos")
card(c8, "Worst Day",         f"-£{abs(worst_day):.2f}",   "neg")

st.markdown("<br>", unsafe_allow_html=True)

# ─── ROW 2: CUMULATIVE + RISK vs RETURN ────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown('<div class="section-title">📉 Cumulative P&L</div>', unsafe_allow_html=True)
    cum_df = filtered.groupby('DateKey')['P/L'].sum().reset_index().sort_values('DateKey')
    cum_df['Cumulative'] = cum_df['P/L'].cumsum()
    cum_df['Date'] = pd.to_datetime(cum_df['DateKey'])
    fig_cum = go.Figure()
    fig_cum.add_trace(go.Scatter(
        x=cum_df['Date'], y=cum_df['Cumulative'],
        fill='tozeroy',
        line=dict(color='#1D9E75' if total_pnl >= 0 else '#D85A30', width=2),
        fillcolor='rgba(29,158,117,0.1)' if total_pnl >= 0 else 'rgba(216,90,48,0.1)',
        hovertemplate='%{x|%d %b}<br>Cumulative P&L: £%{y:.2f}<extra></extra>'
    ))
    fig_cum.add_hline(y=0, line_dash="dash", line_color="#ccc", line_width=1)
    fig_cum.update_layout(height=260, margin=dict(l=0,r=0,t=10,b=0),
        xaxis=dict(showgrid=False), yaxis=dict(tickprefix='£', gridcolor='#f5f5f5'),
        plot_bgcolor='white', paper_bgcolor='white')
    st.plotly_chart(fig_cum, use_container_width=True)

with col2:
    st.markdown('<div class="section-title">⚖️ Daily Risk vs Return</div>', unsafe_allow_html=True)
    risk_df = pd.DataFrame({
        'Date': daily_liab_series.index,
        'Liability': daily_liab_series.values,
        'P/L': daily_pnl_series.reindex(daily_liab_series.index).values
    })
    colors = ['#1D9E75' if v >= 0 else '#D85A30' for v in risk_df['P/L']]
    fig_risk = go.Figure()
    fig_risk.add_trace(go.Bar(
        x=risk_df['Date'], y=risk_df['Liability'],
        name='Liability', marker_color='rgba(100,140,255,0.3)',
        hovertemplate='%{x}<br>Liability: £%{y:.2f}<extra></extra>'
    ))
    fig_risk.add_trace(go.Scatter(
        x=risk_df['Date'], y=risk_df['P/L'],
        name='P/L', mode='lines+markers',
        line=dict(color='#1D9E75', width=2),
        marker=dict(color=colors, size=7),
        hovertemplate='%{x}<br>P&L: £%{y:.2f}<extra></extra>'
    ))
    fig_risk.add_hline(y=0, line_dash="dash", line_color="#ccc", line_width=1)
    fig_risk.update_layout(height=260, margin=dict(l=0,r=0,t=10,b=0),
        xaxis=dict(showgrid=False), yaxis=dict(tickprefix='£', gridcolor='#f5f5f5'),
        plot_bgcolor='white', paper_bgcolor='white',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1))
    st.plotly_chart(fig_risk, use_container_width=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─── ROW 3: CALENDAR + DAY DETAIL ──────────────────────────────────────────────
col_cal, col_detail = st.columns([3, 2])

with col_cal:
    st.markdown('<div class="section-title">📅 P&L Calendar</div>', unsafe_allow_html=True)
    months_available = sorted(filtered['Date'].dt.to_period('M').unique().astype(str), reverse=True)
    cal_month = st.selectbox("Month", options=months_available, label_visibility="collapsed")
    cal_year, cal_mon = int(cal_month.split('-')[0]), int(cal_month.split('-')[1])
    month_data = filtered[(filtered['Date'].dt.year==cal_year) & (filtered['Date'].dt.month==cal_mon)]
    day_pnl  = month_data.groupby(month_data['Date'].dt.day)['P/L'].sum()
    day_bets = month_data.groupby(month_data['Date'].dt.day)['BetID'].count()

    days_header = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
    header_html = ''.join([f'<th style="text-align:center;font-size:11px;color:#999;padding:4px;font-weight:500">{d}</th>' for d in days_header])
    first_dow = calendar.monthrange(cal_year, cal_mon)[0]
    days_in_month = calendar.monthrange(cal_year, cal_mon)[1]
    cells = ['<td></td>'] * first_dow

    for d in range(1, days_in_month+1):
        pnl  = day_pnl.get(d, None)
        bets = day_bets.get(d, 0)
        if pnl is not None:
            bg     = '#E1F5EE' if pnl > 0 else '#FAECE7'
            border = '#9FE1CB' if pnl > 0 else '#F5C4B3'
            color  = '#0F6E56' if pnl > 0 else '#C0392B'
            pnl_str = f"{'+'if pnl>=0 else ''}£{abs(pnl):.0f}"
            cell = f'''<td style="padding:2px">
              <div onclick="window.parent.postMessage({{type:'streamlit:setComponentValue',value:'{cal_year}-{str(cal_mon).zfill(2)}-{str(d).zfill(2)}'}},\'*\')"
                style="background:{bg};border:1px solid {border};border-radius:6px;padding:4px;text-align:center;min-height:54px;cursor:pointer">
                <div style="font-size:11px;color:#999">{d}</div>
                <div style="font-size:12px;font-weight:700;color:{color}">{pnl_str}</div>
                <div style="font-size:10px;color:#aaa">{bets}b</div>
              </div></td>'''
        else:
            cell = f'<td style="padding:2px"><div style="border:1px solid #f0f0f0;border-radius:6px;padding:4px;text-align:center;min-height:54px"><div style="font-size:11px;color:#ddd">{d}</div></div></td>'
        cells.append(cell)

    while len(cells) % 7 != 0:
        cells.append('<td></td>')
    rows_html = ''
    for i in range(0, len(cells), 7):
        rows_html += '<tr>' + ''.join(cells[i:i+7]) + '</tr>'
    st.markdown(f'<table style="width:100%;border-collapse:separate;border-spacing:0"><thead><tr>{header_html}</tr></thead><tbody>{rows_html}</tbody></table>', unsafe_allow_html=True)

    # Day selector via selectbox
    st.markdown("<br>", unsafe_allow_html=True)
    days_with_data = sorted(month_data['Date'].dt.day.unique())
    if days_with_data:
        selected_day_num = st.selectbox(
            "🔍 Click a day to analyse",
            options=days_with_data,
            format_func=lambda d: f"{str(d).zfill(2)} {calendar.month_abbr[cal_mon]} {cal_year}",
            index=len(days_with_data)-1
        )

with col_detail:
    st.markdown('<div class="section-title">📋 Day Analysis</div>', unsafe_allow_html=True)
    if days_with_data:
        selected_date = datetime(cal_year, cal_mon, selected_day_num)
        day_bets_df = month_data[month_data['Date'].dt.day == selected_day_num]
        day_total   = day_bets_df['P/L'].sum()
        day_liab    = day_bets_df['Liability'].sum()
        day_wins    = (day_bets_df['Outcome']=='WIN').sum()
        day_roi     = (day_total / day_liab * 100) if day_liab > 0 else 0

        label_color = "#0F6E56" if day_total >= 0 else "#C0392B"
        st.markdown(f"""
        <div style="background:#f8f9fa;border-radius:8px;padding:12px;margin-bottom:12px;border:1px solid #eee">
            <div style="font-size:13px;color:#666;margin-bottom:2px">{selected_date.strftime('%A, %d %B %Y')}</div>
            <div style="font-size:28px;font-weight:700;color:{label_color}">{'+'if day_total>=0 else ''}£{day_total:.2f}</div>
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:10px">
                <div style="text-align:center"><div style="font-size:11px;color:#999">Bets</div><div style="font-weight:600">{len(day_bets_df)}</div></div>
                <div style="text-align:center"><div style="font-size:11px;color:#999">Wins</div><div style="font-weight:600">{day_wins}/{len(day_bets_df)}</div></div>
                <div style="text-align:center"><div style="font-size:11px;color:#999">ROI</div><div style="font-weight:600">{day_roi:+.1f}%</div></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        for _, bet in day_bets_df.iterrows():
            pnl_color = "#0F6E56" if bet['P/L'] >= 0 else "#C0392B"
            bg = "#f0faf5" if bet['P/L'] >= 0 else "#fdf0ee"
            st.markdown(f"""
            <div class="day-bet-row" style="background:{bg}">
                <div style="font-weight:600;font-size:12px">{bet['Event']}</div>
                <div style="color:#888;font-size:11px">{bet['Market']} · {bet['Selection']} · {bet['Type']} @ {bet['Avg Odds']:.2f}</div>
                <div style="display:flex;justify-content:space-between;margin-top:4px">
                    <span style="font-size:11px;color:#aaa">Liability: £{bet['Liability']:.2f}</span>
                    <span style="font-weight:700;color:{pnl_color}">{'+'if bet['P/L']>=0 else ''}£{bet['P/L']:.2f}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ─── ROW 4: MARKET P&L + THIS WEEK DOW ────────────────────────────────────────
col_a, col_b = st.columns(2)

with col_a:
    st.markdown('<div class="section-title">🏷️ P&L by Market Type</div>', unsafe_allow_html=True)
    market_stats = filtered.groupby('Market').agg(
        PnL=('P/L','sum'),
        Bets=('BetID','count'),
        Wins=('Outcome', lambda x: (x=='WIN').sum())
    ).reset_index()
    market_stats['WinRate'] = (market_stats['Wins'] / market_stats['Bets'] * 100).round(1)
    market_stats = market_stats.sort_values('PnL')
    fig_market = go.Figure(go.Bar(
        x=market_stats['PnL'], y=market_stats['Market'],
        orientation='h',
        marker_color=['#1D9E75' if v>=0 else '#D85A30' for v in market_stats['PnL']],
        hovertemplate='<b>%{y}</b><br>P&L: £%{x:.2f}<extra></extra>'
    ))
    fig_market.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=0),
        xaxis=dict(tickprefix='£', gridcolor='#f5f5f5'),
        yaxis=dict(showgrid=False),
        plot_bgcolor='white', paper_bgcolor='white')
    st.plotly_chart(fig_market, use_container_width=True)

with col_b:
    st.markdown('<div class="section-title">📆 P&L by Day of Week — This Week</div>', unsafe_allow_html=True)
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    week_end   = week_start + timedelta(days=6)
    this_week  = filtered[(filtered['Date'] >= week_start) & (filtered['Date'] <= week_end)]

    dow_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
    if not this_week.empty:
        dow_pnl = this_week.groupby('DayOfWeek')['P/L'].sum().reindex(dow_order).fillna(0)
        fig_dow = go.Figure(go.Bar(
            x=dow_pnl.index, y=dow_pnl.values,
            marker_color=['#1D9E75' if v>=0 else '#D85A30' for v in dow_pnl.values],
            hovertemplate='%{x}<br>P&L: £%{y:.2f}<extra></extra>'
        ))
        fig_dow.add_hline(y=0, line_dash="dash", line_color="#ccc", line_width=1)
        fig_dow.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=0),
            xaxis=dict(showgrid=False),
            yaxis=dict(tickprefix='£', gridcolor='#f5f5f5'),
            plot_bgcolor='white', paper_bgcolor='white')
        st.plotly_chart(fig_dow, use_container_width=True)
        week_total = this_week['P/L'].sum()
        st.caption(f"Week of {week_start.strftime('%d %b')} — {week_end.strftime('%d %b %Y')} · Total: {'+'if week_total>=0 else ''}£{week_total:.2f}")
    else:
        st.info(f"No bets found this week ({week_start.strftime('%d %b')} – {week_end.strftime('%d %b')}). Showing all-time by day of week instead.")
        dow_pnl_all = filtered.groupby('DayOfWeek')['P/L'].sum().reindex(dow_order).fillna(0)
        fig_dow2 = go.Figure(go.Bar(
            x=dow_pnl_all.index, y=dow_pnl_all.values,
            marker_color=['#1D9E75' if v>=0 else '#D85A30' for v in dow_pnl_all.values],
            hovertemplate='%{x}<br>P&L: £%{y:.2f}<extra></extra>'
        ))
        fig_dow2.update_layout(height=240, margin=dict(l=0,r=0,t=10,b=0),
            xaxis=dict(showgrid=False),
            yaxis=dict(tickprefix='£', gridcolor='#f5f5f5'),
            plot_bgcolor='white', paper_bgcolor='white')
        st.plotly_chart(fig_dow2, use_container_width=True)
