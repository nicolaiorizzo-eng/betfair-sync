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

  .bet-row { border-radius:7px; padding:8px 10px; margin-bottom:5px; font-size:12px; border-left:3px solid #ccc; }
  .bet-row.win  { background:#f0faf5; border-left-color:#0F6E56; }
  .bet-row.loss { background:#fdf0ee; border-left-color:#C0392B; }

  section[data-testid="stSidebar"] { background:#1a1a2e !important; }
  section[data-testid="stSidebar"] * { color:#eee !important; }

  /* ── UNIFORM CALENDAR BUTTON STYLING ── */
  button[aria-label*="🟢"], button[aria-label*="🔴"], button[aria-label*="⚪"] {
    min-height:85px !important; 
    height:85px !important;
    border-radius:12px !important; 
    padding:8px 10px !important; 
    width:100% !important;
    transition: transform 0.1s, box-shadow 0.1s !important;
    border: 1.5px solid transparent !important;
  }

  /* Target internal container for layout control */
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
    font-size: 13px !important;
    font-weight: 800 !important;
    line-height: 1.4 !important;
  }

  /* Force top-left alignment on the day number string segment */
  button[aria-label*="🟢"] div[data-testid="stMarkdownContainer"] p::first-line,
  button[aria-label*="🔴"] div[data-testid="stMarkdownContainer"] p::first-line,
  button[aria-label*="⚪"] div[data-testid="stMarkdownContainer"] p::first-line {
    font-size: 11px !important;
    font-weight: 700 !important;
    float: left !important;
    display: block !important;
    width: 100% !important;
    text-align: left !important;
    margin-bottom: 4px !important;
  }

  /* Green Days (Profit) */
  button[aria-label*="🟢"] {
    background: linear-gradient(135deg, #d4f5e9, #a8ead0) !important;
    border: 1.5px solid #5fcca8 !important; 
    color: #0F6E56 !important;
    box-shadow: 0 2px 6px rgba(95,204,168,0.25) !important;
  }
  button[aria-label*="🟢"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 5px 12px rgba(95,204,168,0.4) !important;
  }

  /* Red Days (Loss) */
  button[aria-label*="🔴"] {
    background: linear-gradient(135deg, #fde8e4, #f9c4bb) !important;
    border: 1.5px solid #e8836c !important; 
    color: #C0392B !important;
    box-shadow: 0 2px 6px rgba(232,131,108,0.25) !important;
  }
  button[aria-label*="🔴"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 5px 12px rgba(232,131,108,0.4) !important;
  }

  /* White Days (Empty/No Trades) */
  button[aria-label*="⚪"] {
    background: linear-gradient(135deg, #ffffff, #f6f7f9) !important;
    border: 1.5px solid #e4e7ec !important; 
    color: #a0aec0 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.02) !important;
  }
  button[aria-label*="⚪"]:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 10px rgba(0,0,0,0.08) !important;
    border-color: #cbd5e1 !important;
  }

  /* Primary State Overrides (When Selected) */
  button[aria-label*="🟢"][data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #a8ead0, #5fcca8) !important;
    border: 2px solid #0F6E56 !important;
    outline: 2.5px solid #0F6E56 !important; outline-offset: 1px !important;
  }
  button[aria-label*="🔴"][data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #f9c4bb, #e8836c) !important;
    border: 2px solid #C0392B !important;
    outline: 2.5px solid #C0392B !important; outline-offset: 1px !important;
  }
  button[aria-label*="⚪"][data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #e4e7ec, #cbd5e1) !important;
    border: 2px solid #718096 !important;
    outline: 2.5px solid #718096 !important; outline-offset: 1px !important;
    color: #4a5568 !important;
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
