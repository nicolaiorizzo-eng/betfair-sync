# Betfair Trading Dashboard

## Local setup
```
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Cloud (free)
1. Push this folder to your GitHub repo
2. Go to https://share.streamlit.io
3. Connect your GitHub repo
4. Set secrets (Settings → Secrets):
```
GOOGLE_CREDENTIALS_JSON = "paste your full google credentials JSON here"
GOOGLE_SHEET_NAME = "Professional Trading WB"
```
5. Deploy — you get a free public URL!
