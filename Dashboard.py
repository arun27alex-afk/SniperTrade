import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import pandas as pd
import numpy as np
from fyers_apiv3 import fyersModel
import datetime
import time

# ==========================================
# ⚠️ UPDATE YOUR FYERS API DETAILS HERE ⚠️
# ==========================================
CLIENT_ID = "***"       
SECRET_KEY = "***"         
REDIRECT_URI = "https://snipertrade-9sqhw3vstzhpvpnmyz4n5y.streamlit.app/" 
# ==========================================

st.set_page_config(page_title="Sniper Trade App - Nifty 50", page_icon="🎯", layout="wide")

# --- STRATEGY FUNCTIONS & AUDIO ALERT LOGIC ---
def play_alert_sound():
    sound_url = "https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3"
    audio_html = f"""
        <audio autoplay="true">
            <source src="{sound_url}" type="audio/mpeg">
        </audio>
    """
    st.components.v1.html(audio_html, width=0, height=0, scrolling=False)

def get_ce_signal_and_checklist(data, atr_min=4):
    score = 0
    checklist = {}
    
    # 1. EMA (2 pts)
    if data['EMA_9'] > data['EMA_21']:
        score += 2; checklist["EMA 9/21 (9 EMA > 21 EMA) [+2 pts]"] = True
    else: checklist["EMA 9/21 (9 EMA > 21 EMA) [+2 pts]"] = False
        
    # 2. VWAP (2 pts)
    if data['Close'] > data['VWAP']:
        score += 2; checklist["VWAP (Price > VWAP) [+2 pts]"] = True
    else: checklist["VWAP (Price > VWAP) [+2 pts]"] = False
        
    # 3. ATR Sideways Filter (2 pts) -> Nifty 5-min realistic ATR is usually 4 to 15
    if data['ATR'] > atr_min:
        score += 2; checklist[f"ATR Momentum (> {atr_min}) [+2 pts]"] = True
    else: checklist[f"ATR Momentum (> {atr_min}) [+2 pts]"] = False
        
    # 4. MACD (2 pts)
    if data['MACD_Line'] > data['Signal_Line']:
        score += 2; checklist["MACD (MACD > Signal) [+2 pts]"] = True
    else: checklist["MACD (MACD > Signal) [+2 pts]"] = False
        
    # 5. RSI (1 pt)
    if data['RSI'] > 60:
        score += 1; checklist["RSI (> 60 Bullish) [+1 pt]"] = True
    else: checklist["RSI (> 60 Bullish) [+1 pt]"] = False
        
    # 6. Volume Surge (1 pt) -> 1.5x of Average Volume
    if data['Volume'] > (data['Volume_SMA_20'] * 1.5):
        score += 1; checklist["Volume Surge (> 1.5x Avg) [+1 pt]"] = True
    else: checklist["Volume Surge (> 1.5x Avg) [+1 pt]"] = False
    
    return score, checklist

def get_pe_signal_and_checklist(data, atr_min=4):
    score = 0
    checklist = {}
    
    # 1. EMA (2 pts)
    if data['EMA_9'] < data['EMA_21']:
        score += 2; checklist["EMA 9/21 (9 EMA < 21 EMA) [+2 pts]"] = True
    else: checklist["EMA 9/21 (9 EMA < 21 EMA) [+2 pts]"] = False
        
    # 2. VWAP (2 pts)
    if data['Close'] < data['VWAP']:
        score += 2; checklist["VWAP (Price < VWAP) [+2 pts]"] = True
    else: checklist["VWAP (Price < VWAP) [+2 pts]"] = False
        
    # 3. ATR Sideways Filter (2 pts)
    if data['ATR'] > atr_min:
        score += 2; checklist[f"ATR Momentum (> {atr_min}) [+2 pts]"] = True
    else: checklist[f"ATR Momentum (> {atr_min}) [+2 pts]"] = False
        
    # 4. MACD (2 pts)
    if data['MACD_Line'] < data['Signal_Line']:
        score += 2; checklist["MACD (MACD < Signal) [+2 pts]"] = True
    else: checklist["MACD (MACD < Signal) [+2 pts]"] = False
        
    # 5. RSI (1 pt)
    if data['RSI'] < 40:
        score += 1; checklist["RSI (< 40 Bearish) [+1 pt]"] = True
    else: checklist["RSI (< 40 Bearish) [+1 pt]"] = False
        
    # 6. Volume Surge (1 pt) -> 1.5x of Average Volume
    if data['Volume'] > (data['Volume_SMA_20'] * 1.5):
        score += 1; checklist["Volume Surge (> 1.5x Avg) [+1 pt]"] = True
    else: checklist["Volume Surge (> 1.5x Avg) [+1 pt]"] = False
    
    return score, checklist
# -----------------------------------------------

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
        
        df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
        
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
        
        # --- ATR Calculation ---
        df['Prev_Close'] = df['Close'].shift(1)
        tr1 = df['High'] - df['Low']
        tr2 = (df['High'] - df['Prev_Close']).abs()
        tr3 = (df['Low'] - df['Prev_Close']).abs()
        df['TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        df['ATR'] = df['TR'].rolling(window=14).mean()
        df['ATR'] = df['ATR'].fillna(10) # default value to avoid errors
        
        df = df.round(2)
        
        # --- 🤖 AUTO-BACKTEST LOGIC ---
        total_signals_today = 0
        targets_hit_today = 0
        sl_hit_today = 0
        cost_to_cost_today = 0
        active_trades = []

        for i in range(1, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            
            for t in active_trades[:]:
                if t['type'] == 'LONG':
                    # Step TSL Logic - Move SL to entry if price goes up by 1.5x ATR
                    if not t['tsl_activated'] and row['High'] >= t['entry'] + t['atr_val']:
                        t['sl'] = t['entry'] 
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
                    if not t['tsl_activated'] and row['Low'] <= t['entry'] - t['atr_val']:
                        t['sl'] = t['entry'] 
                        t['tsl_activated'] = True
                        
                    if row['Low'] <= t['target']:
                        targets_hit_today += 1
                        active_trades.remove(t)
                    elif row['High'] >= t['sl']:
                        if t['tsl_activated']: cost_to_cost_today += 1
                        else: sl_hit_today += 1
                        active_trades.remove(t)
                        
            # Backtest Signal Logic (Score >= 7 is STRONG)
            ce_score, _ = get_ce_signal_and_checklist(row)
            pe_score, _ = get_pe_signal_and_checklist(row)
            prev_ce_score, _ = get_ce_signal_and_checklist(prev_row)
            prev_pe_score, _ = get_pe_signal_and_checklist(prev_row)
            
            # Dynamic SL and Target points based on ATR (for Spot Backtesting)
            sl_points = round(1.5 * row['ATR'], 2)
            target_points = round(2.5 * row['ATR'], 2)
            
            if ce_score >= 7 and prev_ce_score < 7:
                total_signals_today += 1
                active_trades.append({'type': 'LONG', 'entry': row['Close'], 'target': row['Close'] + target_points, 'sl': row['Close'] - sl_points, 'atr_val': row['ATR'], 'tsl_activated': False})
            elif pe_score >= 7 and prev_pe_score < 7:
                total_signals_today += 1
                active_trades.append({'type': 'SHORT', 'entry': row['Close'], 'target': row['Close'] - target_points, 'sl': row['Close'] + sl_points, 'atr_val': row['ATR'], 'tsl_activated': False})

        # --- 📌 LIVE SCORECARD DASHBOARD ---
        st.subheader("📊 Today's Auto-Backtest Scorecard")
        col1, col2, col3, col4, col5 = st.columns(5)
        
        with col1: st.metric("Signals Triggered", total_signals_today)
        with col2: st.metric("🎯 Targets Hit", targets_hit_today)
        with col3: st.metric("🛡️ Cost-to-Cost (Zero Loss)", cost_to_cost_today)
        with col4: st.metric("🛑 Stop Loss Hit", sl_hit_today)
        with col5:
            total_closed = targets_hit_today + sl_hit_today + cost_to_cost_today
            win_rate = (targets_hit_today / total_closed * 100) if total_closed > 0 else 0
            st.metric("🏆 Win Rate (%)", f"{win_rate:.1f}%")
        st.markdown("---")

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        close = latest['Close']
        current_atr = latest['ATR']
        
        # Premium SL and Target Calculation (1.5x and 2.5x of ATR applied to Premium)
        # Using Spot ATR directly as premium point movements for simplicity and accuracy
        prem_sl_points = round(1.5 * current_atr, 2)
        prem_target_points = round(2.5 * current_atr, 2)
        
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
        signal_time = latest['Timestamp'].strftime('%I:%M %p') if 'Timestamp' in df.columns else "Live"
        
        # Calculate Current Scores
        ce_score, ce_checklist = get_ce_signal_and_checklist(latest)
        pe_score, pe_checklist = get_pe_signal_and_checklist(latest)
        
        def get_premium(opt_type):
            symbol = f"NSE:NIFTY{expiry_str}{atm_strike}{opt_type}"
            try:
                quote_res = fyers.quotes(data={"symbols": symbol})
                if quote_res.get("s") == "ok":
                    return quote_res['d'][0]['v']['lp']
            except:
                pass
            return 0.0

        if ce_score >= 7:
            play_alert_sound()
            premium = get_premium("CE")
            opt_symbol = f"NSE:NIFTY{expiry_str}{atm_strike}CE"
            
            st.success(f"### 🟢 MARKET GOING UP - BUY CE (Score: {ce_score}/10) @ {signal_time}")
            
            st.markdown("### 📊 Indicator Checklist")
            for indicator, is_matched in ce_checklist.items():
                if is_matched: st.markdown(f"✅ **{indicator}**: Aligned")
                else: st.markdown(f"❌ **{indicator}**: Not Aligned")
            
            if premium > 0:
                t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns(5)
                t_col1.metric("📌 Strike Rate", f"{atm_strike} CE")
                t_col2.metric("🚪 Entry Price", f"₹{premium}")
                t_col3.metric(f"🎯 Target (+{prem_target_points})", f"₹{round(premium + prem_target_points, 2)}")
                t_col4.metric(f"🛑 Stop Loss (-{prem_sl_points})", f"₹{round(premium - prem_sl_points, 2)}")
                t_col5.metric("⏰ Signal Time", signal_time)
                
                st.info(f"💡 **Safe Entry Range:** ₹{premium} to ₹{round(premium + 4, 2)} only! \n"
                        f"⚠️ **Warning:** If the premium crosses above ₹{round(premium + 4, 2)}, please DO NOT enter this trade (Avoid Chasing)!")
                
                st.write("")
                if st.button(f"🚀 BUY {atm_strike} CE NOW ({num_lots} Lot)", type="primary", use_container_width=True):
                    order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                    order_res = fyers.place_order(data=order_data)
                    if order_res.get("s") == "ok": st.balloons(); st.success(f"✅ Order Placed Successfully! ID: {order_res.get('id')}")
                    else: st.error(f"❌ Order Failed: {order_res.get('message')}")
            else:
                st.warning(f"Strike: {atm_strike} CE - **Market Closed or Expiry Incorrect**")
                
        elif pe_score >= 7:
            play_alert_sound()
            premium = get_premium("PE")
            opt_symbol = f"NSE:NIFTY{expiry_str}{atm_strike}PE"
            
            st.error(f"### 🔴 MARKET GOING DOWN - BUY PE (Score: {pe_score}/10) @ {signal_time}")
            
            st.markdown("### 📊 Indicator Checklist")
            for indicator, is_matched in pe_checklist.items():
                if is_matched: st.markdown(f"✅ **{indicator}**: Aligned")
                else: st.markdown(f"❌ **{indicator}**: Not Aligned")
            
            if premium > 0:
                t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns(5)
                t_col1.metric("📌 Strike Rate", f"{atm_strike} PE")
                t_col2.metric("🚪 Entry Price", f"₹{premium}")
                t_col3.metric(f"🎯 Target (+{prem_target_points})", f"₹{round(premium + prem_target_points, 2)}")
                t_col4.metric(f"🛑 Stop Loss (-{prem_sl_points})", f"₹{round(premium - prem_sl_points, 2)}")
                t_col5.metric("⏰ Signal Time", signal_time)
                
                st.info(f"💡 **Safe Entry Range:** ₹{premium} to ₹{round(premium + 4, 2)} only! \n"
                        f"⚠️ **Warning:** If the premium crosses above ₹{round(premium + 4, 2)}, please DO NOT enter this trade (Avoid Chasing)!")
                
                st.write("")
                if st.button(f"🚀 BUY {atm_strike} PE NOW ({num_lots} Lot)", type="primary", use_container_width=True):
                    order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                    order_res = fyers.place_order(data=order_data)
                    if order_res.get("s") == "ok": st.balloons(); st.success(f"✅ Order Placed Successfully! ID: {order_res.get('id')}")
                    else: st.error(f"❌ Order Failed: {order_res.get('message')}")
            else:
                st.warning(f"Strike: {atm_strike} PE - **Market Closed or Expiry Incorrect**")
                
        else:
            st.warning(f"### 🟡 WAITING FOR PERFECT SETUP")
            st.markdown(f"**Current Trend is Weak or Sideways.** \n* **CE Score:** {ce_score}/10 \n* **PE Score:** {pe_score}/10")
            st.markdown(f"* ATR (Volatility): {current_atr:.2f} | RSI: {latest['RSI']:.2f} | Spot: {close}")

        # --- 📊 PRO INTERACTIVE CHART ---
        st.markdown("---")
        st.subheader("📊 Live NIFTY 50 Pro Chart")
        
        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.75, 0.25])

        fig.add_trace(go.Candlestick(x=df['Timestamp'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Candles'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['VWAP'], line=dict(color='#795548', width=2, dash='dash'), name='VWAP'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['EMA_9'], line=dict(color='#2196f3', width=1.5), name='EMA 9'), row=1, col=1)
        fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['EMA_21'], line=dict(color='#f44336', width=1.5), name='EMA 21'), row=1, col=1)

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
