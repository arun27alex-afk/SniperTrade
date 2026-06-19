import plotly.graph_objects as go
import streamlit as st
import pandas as pd
from fyers_apiv3 import fyersModel
import datetime

# ==========================================
# ⚠️ UPDATE YOUR FYERS API DETAILS HERE ⚠️
# ==========================================
CLIENT_ID = "BT8FRQLN19-200"       
SECRET_KEY = "0ivLeQN8vdI2VyKA"         
REDIRECT_URI = "https://snipertrade-9sqhw3vstzhpvpnmyz4n5y.streamlit.app/" 
# ==========================================

st.set_page_config(page_title="Sniper Trade App", page_icon="🎯", layout="wide")
st.title("🎯 Sniper Trade App (Pro Strategy Signals)")
st.markdown("---")

if 'access_token' not in st.session_state:
    st.session_state['access_token'] = None

query_params = st.query_params
if "auth_code" in query_params:
    auth_code = query_params["auth_code"]
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID, secret_key=SECRET_KEY, 
        redirect_uri=REDIRECT_URI, response_type="code", grant_type="authorization_code"
    )
    session.set_token(auth_code)
    response = session.generate_token()
    if response.get("s") == "ok":
        st.session_state['access_token'] = response["access_token"]
        st.success("✅ Fyers Connected Successfully!")
    else:
        st.error("Login Failed. Please try again.")

if not st.session_state['access_token']:
    st.subheader("🔑 Step 1: 1-Click Fyers Login")
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, 
        response_type="code", grant_type="authorization_code"
    )
    auth_url = session.generate_authcode()
    st.markdown(f"**[👉 Click Here to Login to Fyers]({auth_url})**")

if st.session_state['access_token']:
    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, is_async=False, token=st.session_state['access_token'], log_path="")
    
    today_date = datetime.date.today().strftime('%Y-%m-%d')
    data = {
        "symbol": "NSE:NIFTY50-INDEX", 
        "resolution": "5",
        "date_format": "1",
        "range_from": today_date,
        "range_to": today_date,
        "cont_flag": "1"
    }
    res = fyers.history(data=data)
    
    if res.get("s") == "ok":
        df = pd.DataFrame(res['candles'])
        df.columns = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata').dt.strftime('%H:%M')
        
        # --- Indicators ---
        df['EMA_20'] = df['Close'].ewm(span=20, adjust=False).mean()
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (df['Typical_Price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
        df['VWAP'] = df['VWAP'].fillna(df['Close']) 
        
        df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
        df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD_Line'] = df['EMA_12'] - df['EMA_26']
        df['Signal_Line'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
        
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        df['RSI'] = df['RSI'].fillna(50)
        
        df = df.round(2)
        
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        close = latest['Close']
        
        # --- 📌 Dynamic Sidebar Menu ---
        with st.sidebar:
            st.header("📈 Live Market")
            st.markdown("---")
            change = close - prev['Close']
            # This Nifty value is now dynamically mapped to the latest Close price!
            st.metric(label="NIFTY 50 (Spot)", value=f"{close:,.2f}", delta=f"{change:.2f}")
            st.markdown("---")
            st.info("💡 Next Step: Connecting Live Fyers Options Premium.")

        # --- 🎯 PRO SIGNAL & TARGET UI ---
        st.markdown("---")
        st.subheader("🎯 Live Signal System")
        
        atm_strike = int(round(close / 50) * 50) 
        
        # 60/40 RSI Logic implemented here
        macd_bullish = latest['MACD_Line'] > latest['Signal_Line']
        macd_bearish = latest['MACD_Line'] < latest['Signal_Line']
        
        long_condition = (latest['RSI'] > 60) and (close > latest['VWAP']) and macd_bullish
        short_condition = (latest['RSI'] < 40) and (close < latest['VWAP']) and macd_bearish
        
        if long_condition:
            st.success(f"### 🟢 STRONG BUY SIGNAL")
            st.markdown(f"""
            **Index Spot Price:** {close}
            * **Buy Strike:** `{atm_strike} CE`
            * **Entry Zone (Spot):** {close - 5} to {close + 5}
            * **Target (Spot):** {close + 40}
            * **Stop Loss (Spot):** {close - 20}
            
            *(Note: Live Options Premium Price will be integrated here next!)*
            """)
            
        elif short_condition:
            st.error(f"### 🔴 STRONG SELL SIGNAL")
            st.markdown(f"""
            **Index Spot Price:** {close}
            * **Buy Strike:** `{atm_strike} PE`
            * **Entry Zone (Spot):** {close - 5} to {close + 5}
            * **Target (Spot):** {close - 40}
            * **Stop Loss (Spot):** {close + 20}
            
            *(Note: Live Options Premium Price will be integrated here next!)*
            """)
            
        else:
            st.warning(f"### 🟡 WAITING FOR PERFECT SETUP")
            st.markdown(f"**Current Trend is Weak.** \n* Spot Price: {close} \n* RSI: {latest['RSI']} (Needs to cross 60 for Buy, or break 40 for Sell)")

        # --- 📊 Live Market Chart ---
        st.markdown("---")
        st.subheader("📊 Live Market Chart")
        fig = go.Figure(data=[go.Candlestick(x=df['Timestamp'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Candlestick')])
        fig.update_traces(increasing_line_color='#26a69a', increasing_fillcolor='#26a69a', decreasing_line_color='#ef5350', decreasing_fillcolor='#ef5350')
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['VWAP'], line=dict(color='#795548', width=1.5, dash='dash'), name='VWAP'))

        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=600, margin=dict(l=10, r=50, t=30, b=30),
            dragmode='pan',
            xaxis=dict(gridcolor='#f2f2f2', linecolor='#e0e0e0', rangeslider_visible=False),
            yaxis=dict(gridcolor='#f2f2f2', linecolor='#e0e0e0', side='right', fixedrange=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
        )
        st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True, 'displayModeBar': True})
