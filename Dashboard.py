import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import pandas as pd
from fyers_apiv3 import fyersModel
import datetime
import time

# ==========================================
# ⚠️ UPDATE YOUR FYERS API DETAILS HERE ⚠️
# ==========================================
CLIENT_ID = "BT8FRQLN19-200"       
SECRET_KEY = "0ivLeQN8vdI2VyKA"         
REDIRECT_URI = "https://snipertrade-9sqhw3vstzhpvpnmyz4n5y.streamlit.app/" 
# ==========================================

st.set_page_config(page_title="Sniper Trade App - Nifty 50", page_icon="🎯", layout="wide")
st.title("🎯 Sniper Trade App (NIFTY 50 Live & Algo Execution)")
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
        
        # Keep Datetime for correct Zooming on Time Axis
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
        
        # --- Indicators ---
        df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
        df['VWAP'] = (df['Typical_Price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
        df['VWAP'] = df['VWAP'].fillna(df['Close']) 
        
        df['MA_20'] = df['Close'].rolling(window=20).mean()
        df['MA_50'] = df['Close'].rolling(window=50).mean()
        
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
        
        # --- 🤖 AUTO-BACKTEST LOGIC (WITH STEP TSL) ---
        total_signals_today = 0
        targets_hit_today = 0
        sl_hit_today = 0
        cost_to_cost_today = 0
        active_trades = []

        df['Prev_RSI'] = df['RSI'].shift(1)
        df['Prev_Close'] = df['Close'].shift(1)
        df['Prev_VWAP'] = df['VWAP'].shift(1)
        df['Prev_MACD'] = df['MACD_Line'].shift(1)
        df['Prev_Signal'] = df['Signal_Line'].shift(1)

        for i in range(1, len(df)):
            row = df.iloc[i]
            
            for t in active_trades[:]:
                if t['type'] == 'LONG':
                    # Step TSL Logic
                    if not t['tsl_activated'] and row['High'] >= t['entry'] + 20:
                        t['sl'] = t['entry'] # Move SL to Cost
                        t['tsl_activated'] = True
                        
                    if row['High'] >= t['target']:
                        targets_hit_today += 1
                        active_trades.remove(t)
                    elif row['Low'] <= t['sl']:
                        if t['tsl_activated']: cost_to_cost_today += 1
                        else: sl_hit_today += 1
                        active_trades.remove(t)
                        
                elif t['type'] == 'SHORT':
                    # Step TSL Logic
                    if not t['tsl_activated'] and row['Low'] <= t['entry'] - 20:
                        t['sl'] = t['entry'] # Move SL to Cost
                        t['tsl_activated'] = True
                        
                    if row['Low'] <= t['target']:
                        targets_hit_today += 1
                        active_trades.remove(t)
                    elif row['High'] >= t['sl']:
                        if t['tsl_activated']: cost_to_cost_today += 1
                        else: sl_hit_today += 1
                        active_trades.remove(t)
                        
            # New Signal Conditions
            macd_bullish = row['MACD_Line'] > row['Signal_Line']
            macd_bearish = row['MACD_Line'] < row['Signal_Line']
            long_cond = (row['RSI'] > 60) and (row['Close'] > row['VWAP']) and macd_bullish
            short_cond = (row['RSI'] < 40) and (row['Close'] < row['VWAP']) and macd_bearish
            
            prev_macd_bullish = row['Prev_MACD'] > row['Prev_Signal']
            prev_macd_bearish = row['Prev_MACD'] < row['Prev_Signal']
            prev_long_cond = (row['Prev_RSI'] > 60) and (row['Prev_Close'] > row['Prev_VWAP']) and prev_macd_bullish
            prev_short_cond = (row['Prev_RSI'] < 40) and (row['Prev_Close'] < row['Prev_VWAP']) and prev_macd_bearish
            
            if long_cond and not prev_long_cond:
                total_signals_today += 1
                active_trades.append({'type': 'LONG', 'entry': row['Close'], 'target': row['Close'] + 40, 'sl': row['Close'] - 20, 'tsl_activated': False})
            elif short_cond and not prev_short_cond:
                total_signals_today += 1
                active_trades.append({'type': 'SHORT', 'entry': row['Close'], 'target': row['Close'] - 40, 'sl': row['Close'] + 20, 'tsl_activated': False})

        # --- 📌 LIVE SCORECARD DASHBOARD ---
        st.subheader("📊 Today's Auto-Backtest Scorecard")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1: st.metric("Signals Triggered", total_signals_today)
        with col2: st.metric("🎯 Targets (40 Pts)", targets_hit_today)
        with col3: st.metric("🛡️ Cost-to-Cost (Zero Loss)", cost_to_cost_today)
        with col4: st.metric("🛑 Stop Loss (20 Pts)", sl_hit_today)
        with col5:
            total_closed = targets_hit_today + sl_hit_today + cost_to_cost_today
            win_rate = (targets_hit_today / total_closed * 100) if total_closed > 0 else 0
            st.metric("🏆 Win Rate (%)", f"{win_rate:.1f}%")
        st.markdown("---")

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        close = latest['Close']
        
        # --- 📌 Sidebar Menu ---
        with st.sidebar:
            st.header("📈 Live Market")
            st.markdown("---")
            change = close - prev['Close']
            st.metric(label="NIFTY 50 (Spot)", value=f"{close:,.2f}", delta=f"{change:.2f}")
            st.markdown("---")
            st.subheader("⚙️ Options Settings")
            expiry_str = st.text_input("Enter Expiry (e.g., 26JUN)", "26JUN") 
            num_lots = st.number_input("Select Number of Lots", min_value=1, max_value=50, value=1, step=1)
            total_qty = num_lots * 65  
            st.write(f"Total Quantity: **{total_qty} shares**")
            
            st.markdown("---")
            auto_refresh = st.checkbox("🔄 Auto Refresh (10 Sec)", value=True)

        # --- 🎯 LIVE SIGNAL ALERT ---
        st.subheader("🎯 Live Signal Alert")
        
        atm_strike = int(round(close / 50) * 50) 
        macd_bullish_live = latest['MACD_Line'] > latest['Signal_Line']
        macd_bearish_live = latest['MACD_Line'] < latest['Signal_Line']
        
        long_condition_live = (latest['RSI'] > 60) and (close > latest['VWAP']) and macd_bullish_live
        short_condition_live = (latest['RSI'] < 40) and (close < latest['VWAP']) and macd_bearish_live
        
        # Calculate Signal Time
        signal_time = latest['Timestamp'].strftime('%I:%M %p') if 'Timestamp' in df.columns else "Live"
        
        def get_premium(opt_type):
            symbol = f"NSE:NIFTY{expiry_str}{atm_strike}{opt_type}"
            try:
                quote_res = fyers.quotes(data={"symbols": symbol})
                if quote_res.get("s") == "ok":
                    return quote_res['d'][0]['v']['lp']
            except:
                pass
            return 0.0

        if long_condition_live:
            premium = get_premium("CE")
            opt_symbol = f"NSE:NIFTY{expiry_str}{atm_strike}CE"
            st.success(f"### 🟢 MARKET GOING UP - BUY CE (Signal Alert @ {signal_time})")
            
            if premium > 0:
                st.markdown(f"**Symbol:** `{opt_symbol}`")
                
                t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns(5)
                t_col1.metric("📌 Strike Rate", f"{atm_strike} CE")
                t_col2.metric("🚪 Entry Price", f"₹{premium}")
                t_col3.metric("🎯 Target (+40)", f"₹{round(premium + 40, 2)}")
                t_col4.metric("🛑 Stop Loss (-20)", f"₹{round(premium - 20, 2)}")
                t_col5.metric("⏰ Signal Time", signal_time)
                
                # English Info Alert for Safe Entry
                st.info(f"💡 **Safe Entry Range:** ₹{premium} to ₹{round(premium + 4, 2)} only! \n"
                        f"⚠️ **Warning:** If the premium crosses above ₹{round(premium + 4, 2)}, please DO NOT enter this trade (Avoid Chasing)!")
                
                st.write("") 
                if st.button(f"🚀 BUY {atm_strike} CE NOW ({num_lots} Lot)", type="primary", use_container_width=True):
                    order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                    order_res = fyers.place_order(data=order_data)
                    if order_res.get("s") == "ok":
                        st.balloons()
                        st.success(f"✅ Order Placed Successfully! ID: {order_res.get('id')}")
                    else:
                        st.error(f"❌ Order Failed: {order_res.get('message')}")
            else:
                st.warning(f"Strike: {atm_strike} CE - **Market Closed or Expiry Format Incorrect (Check Expiry: {expiry_str})**")
                
        elif short_condition_live:
            premium = get_premium("PE")
            opt_symbol = f"NSE:NIFTY{expiry_str}{atm_strike}PE"
            st.error(f"### 🔴 MARKET GOING DOWN - BUY PE (Signal Alert @ {signal_time})")
            
            if premium > 0:
                st.markdown(f"**Symbol:** `{opt_symbol}`")
                
                t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns(5)
                t_col1.metric("📌 Strike Rate", f"{atm_strike} PE")
                t_col2.metric("🚪 Entry Price", f"₹{premium}")
                t_col3.metric("🎯 Target (+40)", f"₹{round(premium + 40, 2)}")
                t_col4.metric("🛑 Stop Loss (-20)", f"₹{round(premium - 20, 2)}")
                t_col5.metric("⏰ Signal Time", signal_time)
                
                # English Info Alert for Safe Entry
                st.info(f"💡 **Safe Entry Range:** ₹{premium} to ₹{round(premium + 4, 2)} only! \n"
                        f"⚠️ **Warning:** If the premium crosses above ₹{round(premium + 4, 2)}, please DO NOT enter this trade (Avoid Chasing)!")
                
                st.write("") 
                if st.button(f"🚀 BUY {atm_strike} PE NOW ({num_lots} Lot)", type="primary", use_container_width=True):
                    order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                    order_res = fyers.place_order(data=order_data)
                    if order_res.get("s") == "ok":
                        st.balloons()
                        st.success(f"✅ Order Placed Successfully! ID: {order_res.get('id')}")
                    else:
                        st.error(f"❌ Order Failed: {order_res.get('message')}")
            else:
                st.warning(f"Strike: {atm_strike} PE - **Market Closed or Expiry Format Incorrect (Check Expiry: {expiry_str})**")
                
        else:
            st.warning(f"### 🟡 WAITING FOR PERFECT SETUP")
            st.markdown(f"**Current NIFTY 50 Trend is Weak or Sideways.** \n* Spot Price: {close} \n* RSI: {latest['RSI']:.2f}")

        # --- 📊 PRO INTERACTIVE CHART ---
        st.markdown("---")
        st.subheader("📊 Live NIFTY 50 Pro Chart")
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.75, 0.25])

        fig.add_trace(go.Candlestick(x=df['Timestamp'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Candles'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['VWAP'], line=dict(color='#795548', width=2, dash='dash'), name='VWAP'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['MA_20'], line=dict(color='#2196f3', width=1.5), name='MA 20'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['MA_50'], line=dict(color='#f44336', width=1.5), name='MA 50'), row=1, col=1)

        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['MACD_Line'], line=dict(color='#2196f3', width=1.5), name='MACD'), row=2, col=1)
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['Signal_Line'], line=dict(color='#ff9800', width=1.5), name='Signal'), row=2, col=1)

        fig.update_layout(
            plot_bgcolor='white', paper_bgcolor='white', height=650, margin=dict(l=10, r=10, t=30, b=10),
            dragmode='pan', hovermode='x unified', showlegend=False
        )
        
        fig.update_xaxes(fixedrange=False, rangeslider_visible=False, tickformat="%H:%M")
        fig.update_yaxes(fixedrange=False)

        chart_config = {'scrollZoom': True, 'displayModeBar': True, 'displaylogo': False}
        st.plotly_chart(fig, use_container_width=True, config=chart_config)
        
        # --- 🔄 TRIGGER AUTO REFRESH ---
        if auto_refresh:
            time.sleep(10)
            st.rerun()
