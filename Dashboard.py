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
CLIENT_ID = "OKBFI4WVN5-100"       
SECRET_KEY = "8CZSPWMKOA"  
REDIRECT_URI = "https://snipertrade-9sqhw3vstzhpvpnmyz4n5y.streamlit.app/" 
# ==========================================

st.set_page_config(page_title="Sniper Trade App - NIFTY 50", page_icon="🎯", layout="wide")

if 'data_loaded' not in st.session_state:
    st.session_state['data_loaded'] = False

# --- STRATEGY FUNCTIONS & AUDIO ALERT LOGIC ---
def play_alert_sound():
    sound_url = "https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3"
    audio_html = f"""
        <audio autoplay="true">
            <source src="{sound_url}" type="audio/mpeg">
        </audio>
    """
    st.components.v1.html(audio_html, width=0, height=0, scrolling=False)

def get_ce_signal_and_checklist(data, atr_min=5):
    score = 0
    checklist = {}
    if data['EMA_9'] > data['EMA_21']:
        score += 2; checklist["EMA 9/21 (9 EMA > 21 EMA) [+2 pts]"] = True
    else: checklist["EMA 9/21 (9 EMA > 21 EMA) [+2 pts]"] = False
    if data['Close'] > data['VWAP']:
        score += 2; checklist["VWAP (Price > VWAP) [+2 pts]"] = True
    else: checklist["VWAP (Price > VWAP) [+2 pts]"] = False
    if data['ATR'] > atr_min:
        score += 2; checklist[f"ATR Momentum (> {atr_min}) [+2 pts]"] = True
    else: checklist[f"ATR Momentum (> {atr_min}) [+2 pts]"] = False
    if data['MACD_Line'] > data['Signal_Line']:
        score += 2; checklist["MACD (MACD > Signal) [+2 pts]"] = True
    else: checklist["MACD (MACD > Signal) [+2 pts]"] = False
    if data['ADX_14'] > 20:
        score += 1; checklist["ADX 14 Trend (> 20 Strong) [+1 pt]"] = True
    else: checklist["ADX 14 Trend (> 20 Strong) [+1 pt]"] = False
    if data['Volume'] > (data['Volume_SMA_20'] * 1.2):
        score += 1; checklist["Volume Surge (> 1.2x Avg) [+1 pt]"] = True
    else: checklist["Volume Surge (> 1.2x Avg) [+1 pt]"] = False
    return score, checklist

def get_pe_signal_and_checklist(data, atr_min=5):
    score = 0
    checklist = {}
    if data['EMA_9'] < data['EMA_21']:
        score += 2; checklist["EMA 9/21 (9 EMA < 21 EMA) [+2 pts]"] = True
    else: checklist["EMA 9/21 (9 EMA < 21 EMA) [+2 pts]"] = False
    if data['Close'] < data['VWAP']:
        score += 2; checklist["VWAP (Price < VWAP) [+2 pts]"] = True
    else: checklist["VWAP (Price < VWAP) [+2 pts]"] = False
    if data['ATR'] > atr_min:
        score += 2; checklist[f"ATR Momentum (> {atr_min}) [+2 pts]"] = True
    else: checklist[f"ATR Momentum (> {atr_min}) [+2 pts]"] = False
    if data['MACD_Line'] < data['Signal_Line']:
        score += 2; checklist["MACD (MACD < Signal) [+2 pts]"] = True
    else: checklist["MACD (MACD < Signal) [+2 pts]"] = False
    if data['ADX_14'] > 20:
        score += 1; checklist["ADX 14 Trend (> 20 Strong) [+1 pt]"] = True
    else: checklist["ADX 14 Trend (> 20 Strong) [+1 pt]"] = False
    if data['Volume'] > (data['Volume_SMA_20'] * 1.2):
        score += 1; checklist["Volume Surge (> 1.2x Avg) [+1 pt]"] = True
    else: checklist["Volume Surge (> 1.2x Avg) [+1 pt]"] = False
    return score, checklist

# -----------------------------------------------

st.title("🎯 Sniper Trade App (NIFTY 50 Live & Algo Execution)")
st.markdown("---")

if 'access_token' not in st.session_state:
    st.session_state['access_token'] = None

query_params = st.query_params
if "auth_code" in query_params:
    session = fyersModel.SessionModel(client_id=CLIENT_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URI, response_type="code", grant_type="authorization_code")
    session.set_token(query_params["auth_code"])
    response = session.generate_token()
    if response.get("s") == "ok":
        st.session_state['access_token'] = response["access_token"]
        st.success("✅ Fyers Connected Successfully!")
    else:
        st.error("Login Failed. Please try again.")

if not st.session_state['access_token']:
    st.subheader("🔑 Step 1: 1-Click Fyers Login")
    session = fyersModel.SessionModel(client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, response_type="code", grant_type="authorization_code")
    auth_url = session.generate_authcode()
    st.markdown(f"**[👉 Click Here to Login to Fyers]({auth_url})**")

if st.session_state['access_token']:
    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, is_async=False, token=st.session_state['access_token'], log_path="")
    
    if not st.session_state['data_loaded']:
        st.info("🟢 Fyers Connection Active! Server is ready.")
        st.markdown("Click the button below to safely load market data and start the Algorithm. This prevents the server from crashing.")
        if st.button("🚀 Load Market Data & Start Algo", use_container_width=True, type="primary"):
            st.session_state['data_loaded'] = True
            st.rerun()
    else:
        if st.button("🛑 Stop Algo & Clear Memory", use_container_width=True):
            st.session_state['data_loaded'] = False
            st.rerun()

        today = datetime.date.today()
        if today.weekday() == 5: today_date = (today - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
        elif today.weekday() == 6: today_date = (today - datetime.timedelta(days=2)).strftime('%Y-%m-%d')
        else: today_date = today.strftime('%Y-%m-%d')

        data = {"symbol": "NSE:NIFTY50-INDEX", "resolution": "5", "date_format": "1", "range_from": today_date, "range_to": today_date, "cont_flag": "1"}
        res = fyers.history(data=data)
        
        if res.get("s") == "ok" and 'candles' in res and len(res['candles']) > 0:
            df = pd.DataFrame(res['candles'])
            df.columns = ['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume']
            df.drop_duplicates(subset=['Timestamp'], keep='last', inplace=True)
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
            
            df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
            df['VWAP'] = (df['Typical_Price'] * df['Volume']).cumsum() / df['Volume'].cumsum()
            df['VWAP'] = df['VWAP'].fillna(df['Close']) 
            
            df['EMA_9'] = df['Close'].ewm(span=9, adjust=False).mean()
            df['EMA_21'] = df['Close'].ewm(span=21, adjust=False).mean()
            df['Volume_SMA_20'] = df['Volume'].rolling(window=20).mean()
            
            df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
            df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
            df['MACD_Line'] = df['EMA_12'] - df['EMA_26']
            df['Signal_Line'] = df['MACD_Line'].ewm(span=9, adjust=False).mean()
            
            df['Prev_Close'] = df['Close'].shift(1)
            tr1 = df['High'] - df['Low']
            tr2 = (df['High'] - df['Prev_Close']).abs()
            tr3 = (df['Low'] - df['Prev_Close']).abs()
            df['TR'] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            df['ATR'] = df['TR'].rolling(window=14).mean().fillna(10)
            
            up = df['High'] - df['High'].shift(1)
            down = df['Low'].shift(1) - df['Low']
            df['+DM'] = np.where((up > down) & (up > 0), up, 0.0)
            df['-DM'] = np.where((down > up) & (down > 0), down, 0.0)
            
            df['+DI'] = 100 * (df['+DM'].ewm(alpha=1/14, adjust=False).mean() / df['ATR'])
            df['-DI'] = 100 * (df['-DM'].ewm(alpha=1/14, adjust=False).mean() / df['ATR'])
            
            dx_den = df['+DI'] + df['-DI']
            dx_den = dx_den.replace(0, np.nan) 
            df['DX'] = 100 * (abs(df['+DI'] - df['-DI']) / dx_den)
            df['DX'] = df['DX'].fillna(0)
            df['ADX_14'] = df['DX'].ewm(alpha=1/14, adjust=False).mean().fillna(0)
            
            df = df.round(2)
            
            targets_hit_today = 0
            sl_hit_today = 0
            smart_exits_today = 0
            
            active_trades = []
            trade_history_log = [] 
            buy_x, buy_y, sell_x, sell_y = [], [], [], []
            latest_active_sl, latest_active_tp = None, None

            no_trade_start = datetime.time(12, 0)
            no_trade_end = datetime.time(13, 30)

            for i in range(1, len(df)):
                row = df.iloc[i]
                prev_row = df.iloc[i-1]
                candle_time = row['Timestamp'].time()
                is_valid_time = not (no_trade_start <= candle_time <= no_trade_end)

                for t in active_trades[:]:
                    long = (t['type'] == 'LONG')
                    strike_val = int(round(t['entry'] / 50) * 50)
                    opt_str = "CE" if long else "PE"
                    strike_name = f"{strike_val} {opt_str}"
                    
                    if not t['tsl_activated']:
                        if long and row['High'] >= t['entry'] + t['atr_val']:
                            t['sl'] = t['entry'] + 5 
                            t['tsl_activated'] = True
                        elif not long and row['Low'] <= t['entry'] - t['atr_val']:
                            t['sl'] = t['entry'] - 5 
                            t['tsl_activated'] = True
                    
                    if (long and row['High'] >= t['target']) or (not long and row['Low'] <= t['target']):
                        targets_hit_today += 1
                        trade_history_log.append({"Type": t['type'], "Strike": strike_name, "Entry Time": t['entry_time'].strftime('%I:%M %p'), "Exit Time": row['Timestamp'].strftime('%I:%M %p'), "Entry (Spot)": t['entry'], "Result": "🎯 Target Hit"})
                        active_trades.remove(t)
                        latest_active_sl, latest_active_tp = None, None
                        
                    elif (long and row['Low'] <= t['sl']) or (not long and row['High'] >= t['sl']):
                        if t['tsl_activated']: 
                            smart_exits_today += 1
                            trade_history_log.append({"Type": t['type'], "Strike": strike_name, "Entry Time": t['entry_time'].strftime('%I:%M %p'), "Exit Time": row['Timestamp'].strftime('%I:%M %p'), "Entry (Spot)": t['entry'], "Result": "🧠 Smart Exit (+5)"})
                        else: 
                            sl_hit_today += 1
                            trade_history_log.append({"Type": t['type'], "Strike": strike_name, "Entry Time": t['entry_time'].strftime('%I:%M %p'), "Exit Time": row['Timestamp'].strftime('%I:%M %p'), "Entry (Spot)": t['entry'], "Result": "🛑 SL Hit"})
                        active_trades.remove(t)
                        latest_active_sl, latest_active_tp = None, None

                ce_score, _ = get_ce_signal_and_checklist(row)
                pe_score, _ = get_pe_signal_and_checklist(row)
                prev_ce_score, _ = get_ce_signal_and_checklist(prev_row)
                prev_pe_score, _ = get_pe_signal_and_checklist(prev_row)
                
                sl_points = round(1.5 * row['ATR'], 2)
                target_points = round(2.0 * row['ATR'], 2)

                if ce_score >= 7 and prev_ce_score < 7 and is_valid_time and len(active_trades) == 0:
                    active_trades.append({'type': 'LONG', 'entry': row['Close'], 'target': row['Close'] + target_points, 'sl': row['Close'] - sl_points, 'atr_val': row['ATR'], 'tsl_activated': False, 'entry_time': row['Timestamp']})
                    buy_x.append(row['Timestamp'])
                    buy_y.append(row['Low'] - 15) 
                    latest_active_sl = row['Close'] - sl_points
                    latest_active_tp = row['Close'] + target_points
                    
                elif pe_score >= 7 and prev_pe_score < 7 and is_valid_time and len(active_trades) == 0:
                    active_trades.append({'type': 'SHORT', 'entry': row['Close'], 'target': row['Close'] - target_points, 'sl': row['Close'] + sl_points, 'atr_val': row['ATR'], 'tsl_activated': False, 'entry_time': row['Timestamp']})
                    sell_x.append(row['Timestamp'])
                    sell_y.append(row['High'] + 15) 
                    latest_active_sl = row['Close'] + sl_points
                    latest_active_tp = row['Close'] - target_points

            df_log = pd.DataFrame(trade_history_log).drop_duplicates()
            
            st.subheader("📊 Today's Auto-Backtest Scorecard")
            col1, col2, col3, col4, col5 = st.columns(5)
            
            real_total_signals = len(df_log)
            real_targets_hit = len(df_log[df_log['Result'] == '🎯 Target Hit']) if not df_log.empty else 0
            real_smart_exits = len(df_log[df_log['Result'] == '🧠 Smart Exit (+5)']) if not df_log.empty else 0
            real_sl_hit = len(df_log[df_log['Result'] == '🛑 SL Hit']) if not df_log.empty else 0
            
            with col1: st.metric("Signals Triggered", real_total_signals)
            with col2: st.metric("🎯 Targets Hit", real_targets_hit)
            with col3: st.metric("🧠 Smart Exits (+5)", real_smart_exits)
            with col4: st.metric("🛑 Stop Loss Hit", real_sl_hit)
            with col5:
                total_closed = real_targets_hit + real_sl_hit + real_smart_exits
                win_rate = ((real_targets_hit + real_smart_exits) / total_closed * 100) if total_closed > 0 else 0
                st.metric("🏆 Win Rate (%)", f"{win_rate:.1f}%")
                
            if not df_log.empty:
                with st.expander("📝 View Today's Trade History", expanded=False):
                    st.dataframe(df_log, use_container_width=True)
                    
            st.markdown("---")

            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            close = latest['Close']
            current_atr = latest['ATR']
            
            prem_sl_points = round(1.5 * current_atr, 2)
            prem_target_points = round(2.0 * current_atr, 2)
            
            with st.sidebar:
                st.header("📈 Live Market")
                st.markdown("---")
                st.metric(label="NIFTY 50 (Spot)", value=f"{close:,.2f}", delta=f"{close - prev['Close']:.2f}")
                st.markdown("---")
                st.subheader("⚙️ Options Settings")
                
                def get_next_expiry():
                    today_d = datetime.date.today()
                    days_ahead = 1 - today_d.weekday()
                    if days_ahead < 0: days_ahead += 7
                    next_tue = today_d + datetime.timedelta(days=days_ahead)
                    m_str = str(next_tue.month) if next_tue.month <= 9 else {10: 'O', 11: 'N', 12: 'D'}[next_tue.month]
                    y_str = str(next_tue.year)[-2:]
                    d_str = f"{next_tue.day:02d}"
                    return f"{y_str}{m_str}{d_str}"
                    
                expiry_str = get_next_expiry()
                st.info(f"📅 Auto-Expiry: **{expiry_str}**")
                
                num_lots = st.number_input("Select Number of Lots", min_value=1, max_value=50, value=1, step=1)
                total_qty = num_lots * 65  
                st.write(f"Total Quantity: **{total_qty} shares**")
                st.markdown("---")
                auto_refresh = st.checkbox("🔄 Auto Refresh (10 Sec)", value=True)

                st.markdown("---")
                st.header("📊 Pre-Market Analysis")
                try:
                    start_d = (today - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
                    data_d = {"symbol": "NSE:NIFTY50-INDEX", "resolution": "D", "date_format": "1", "range_from": start_d, "range_to": today_date, "cont_flag": "1"}
                    res_d = fyers.history(data=data_d)
                    if res_d.get("s") == "ok" and len(res_d['candles']) > 0:
                        df_d = pd.DataFrame(res_d['candles'], columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
                        df_d['EMA_9'] = df_d['Close'].ewm(span=9, adjust=False).mean()
                        df_d['EMA_21'] = df_d['Close'].ewm(span=21, adjust=False).mean()
                        last_d = df_d.iloc[-1] 
                        if last_d['EMA_9'] > last_d['EMA_21'] and last_d['Close'] > last_d['EMA_9']:
                            trend_msg = "🟢 UPTREND (Buy on Dips)"
                        elif last_d['EMA_9'] < last_d['EMA_21'] and last_d['Close'] < last_d['EMA_9']:
                            trend_msg = "🔴 DOWNTREND (Sell on Rise)"
                        else:
                            trend_msg = "🟡 SIDEWAYS (Trade with Caution)"
                        st.info(f"**Today's Market Trend:**\n### {trend_msg}")
                        
                        pdh, pdl, pdc = last_d['High'], last_d['Low'], last_d['Close']
                        pp = (pdh + pdl + pdc) / 3
                        r1 = (2 * pp) - pdl
                        s1 = (2 * pp) - pdh
                        ce_strike_range = int(round(r1 / 50) * 50)
                        pe_strike_range = int(round(s1 / 50) * 50)
                        st.success(f"📈 **Max Upside:** {ce_strike_range} CE\n\n📉 **Max Downside:** {pe_strike_range} PE")
                except Exception as e:
                    st.warning("Waiting for Market Data to load...")
                
            st.subheader("🎯 Live Signal & Trade Alerts")
            
            if len(active_trades) > 0:
                current_trade = active_trades[0]
                trade_dir = "📈 CALL (BUY CE)" if current_trade['type'] == 'LONG' else "📉 PUT (BUY PE)"
                active_strike = int(round(current_trade['entry'] / 50) * 50)
                opt_type = "CE" if current_trade['type'] == 'LONG' else "PE"
                opt_symbol = f"NSE:NIFTY{expiry_str}{active_strike}{opt_type}"
                
                live_prem, entry_prem = 0.0, 0.0
                try:
                    quote_res = fyers.quotes(data={"symbols": opt_symbol})
                    if quote_res.get("s") == "ok": live_prem = quote_res['d'][0]['v']['lp']
                except: pass
                
                try:
                    opt_data = {"symbol": opt_symbol, "resolution": "5", "date_format": "1", "range_from": today_date, "range_to": today_date, "cont_flag": "1"}
                    opt_res = fyers.history(data=opt_data)
                    if opt_res.get("s") == "ok" and 'candles' in opt_res:
                        df_opt = pd.DataFrame(opt_res['candles'], columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
                        df_opt['Timestamp'] = pd.to_datetime(df_opt['Timestamp'], unit='s').dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                        match = df_opt[df_opt['Timestamp'] == current_trade['entry_time']]
                        if not match.empty: entry_prem = match.iloc[0]['Close']
                except: pass
                
                trade_atr = current_trade['atr_val']
                prem_target_points = round(2.0 * trade_atr, 2)
                prem_sl_points = round(1.5 * trade_atr, 2)
                target_prem = round(entry_prem + prem_target_points, 2) if entry_prem > 0 else 0.0
                sl_prem = round(entry_prem - prem_sl_points, 2) if entry_prem > 0 else 0.0
                
                st.warning(f"⏳ **ACTIVE TRADE RUNNING:** A {trade_dir} trade is currently active.")
                
                st.markdown("### 📊 Premium Track (Live)")
                t_col1, t_col2, t_col3, t_col4, t_col5 = st.columns(5)
                t_col1.metric("📌 Strike Rate", f"{active_strike} {opt_type}")
                t_col2.metric("🔥 Live Premium", f"₹{live_prem}")
                t_col3.metric("🚪 Premium Entry", f"₹{entry_prem}" if entry_prem > 0 else "Loading...")
                t_col4.metric("🎯 Target", f"₹{target_prem}" if entry_prem > 0 else "-")
                t_col5.metric("🛑 Stop Loss", f"₹{sl_prem}" if entry_prem > 0 else "-")
                st.markdown("---")
            
            if len(active_trades) > 0:
                current_trade = active_trades[-1]
                trade_type = current_trade['type']
                entry_price = current_trade['entry']
                if trade_type == 'LONG': current_profit = close - entry_price
                else: current_profit = entry_price - close
                
                if current_trade['tsl_activated'] == True and 5 <= current_profit <= 10:
                    is_trend_dead = False
                    if trade_type == 'LONG' and close < latest['EMA_9']: is_trend_dead = True 
                    elif trade_type == 'SHORT' and close > latest['EMA_9']: is_trend_dead = True 
                    if is_trend_dead:
                        play_alert_sound()
                        st.error(f"### ⚠️ SMART ALERT: TREND REVERSAL DETECTED!")
                        st.markdown(f"Your Stop Loss is secured at +5 points. You are currently in **+{current_profit:.2f} points profit**.")
                        st.markdown("---")
            
            atm_strike = int(round(close / 50) * 50) 
            signal_time = latest['Timestamp'].strftime('%I:%M %p')
            latest_time_obj = latest['Timestamp'].time()
            is_live_valid_time = not (no_trade_start <= latest_time_obj <= no_trade_end)
            
            ce_score, ce_checklist = get_ce_signal_and_checklist(latest)
            pe_score, pe_checklist = get_pe_signal_and_checklist(latest)
            
            def get_premium(opt_type):
                symbol = f"NSE:NIFTY{expiry_str}{atm_strike}{opt_type}"
                try:
                    quote_res = fyers.quotes(data={"symbols": symbol})
                    if quote_res.get("s") == "ok": return quote_res['d'][0]['v']['lp']
                except: pass
                return 0.0

            if not is_live_valid_time:
                st.warning("⏳ **NO TRADE ZONE (12:00 PM to 1:30 PM)**")
                st.markdown("Market is highly volatile or sideways during this time.")
            elif ce_score >= 7:
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
                    t_col2.metric("🚪 Premium Entry", f"₹{premium}")
                    t_col3.metric(f"🎯 Target (+{prem_target_points})", f"₹{round(premium + prem_target_points, 2)}")
                    t_col4.metric(f"🛑 Stop Loss (-{prem_sl_points})", f"₹{round(premium - prem_sl_points, 2)}")
                    t_col5.metric("⏰ Signal Time", signal_time)
                    st.write("")
                    if st.button(f"🚀 BUY {atm_strike} CE NOW ({num_lots} Lot)", type="primary", use_container_width=True):
                        order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                        order_res = fyers.place_order(data=order_data)
                        if order_res.get("s") == "ok": st.balloons(); st.success("✅ Order Placed Successfully!")
                        else: st.error("❌ Order Failed.")
                else: st.warning(f"Strike: {atm_strike} CE - **Market Closed or Expiry Incorrect**")
                    
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
                    t_col2.metric("🚪 Premium Entry", f"₹{premium}")
                    t_col3.metric(f"🎯 Target (+{prem_target_points})", f"₹{round(premium + prem_target_points, 2)}")
                    t_col4.metric(f"🛑 Stop Loss (-{prem_sl_points})", f"₹{round(premium - prem_sl_points, 2)}")
                    t_col5.metric("⏰ Signal Time", signal_time)
                    st.write("")
                    if st.button(f"🚀 BUY {atm_strike} PE NOW ({num_lots} Lot)", type="primary", use_container_width=True):
                        order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                        order_res = fyers.place_order(data=order_data)
                        if order_res.get("s") == "ok": st.balloons(); st.success("✅ Order Placed Successfully!")
                        else: st.error("❌ Order Failed.")
                else: st.warning(f"Strike: {atm_strike} PE - **Market Closed or Expiry Incorrect**")
            else:
                st.warning(f"### 🟡 WAITING FOR PERFECT SETUP")
                st.markdown(f"**Current Trend is Weak or missing momentum.** \n* **CE Score:** {ce_score}/10 \n* **PE Score:** {pe_score}/10")
                
            st.markdown("---")

            st.subheader("🖥️ Live Market HUD")
            hud_c1, hud_c2, hud_c3, hud_c4 = st.columns(4)
            adx_color = "🟢 Strong Trend" if latest['ADX_14'] > 20 else "🔴 Weak/Sideways"
            atr_color = "🟢 Good Volatility" if current_atr > 5 else "🔴 Sideways (<5)"
            trend_color = "🟢 BUY Zone" if latest['EMA_9'] > latest['EMA_21'] else "🔴 SELL Zone"
            vwap_color = "🟢 Above VWAP" if close > latest['VWAP'] else "🔴 Below VWAP"
            hud_c1.info(f"**ADX (14):** {latest['ADX_14']:.2f} \n\n {adx_color}")
            hud_c2.info(f"**ATR (14):** {current_atr:.2f} \n\n {atr_color}")
            hud_c3.info(f"**Trend (EMA):** \n\n {trend_color}")
            hud_c4.info(f"**VWAP Status:** \n\n {vwap_color}")

            fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.75, 0.25])
            fig.add_trace(go.Candlestick(x=df['Timestamp'], open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name='Candles'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['VWAP'], line=dict(color='#795548', width=2, dash='dash'), name='VWAP'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['EMA_9'], line=dict(color='#2196f3', width=1.5), name='EMA 9'), row=1, col=1)
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['EMA_21'], line=dict(color='#f44336', width=1.5), name='EMA 21'), row=1, col=1)
            
            if len(buy_x) > 0: fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode='markers', marker=dict(symbol='triangle-up', size=16, color='#00e5a0', line=dict(width=1, color='black')), name='BUY Signal'), row=1, col=1)
            if len(sell_x) > 0: fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode='markers', marker=dict(symbol='triangle-down', size=16, color='#ff4d6d', line=dict(width=1, color='black')), name='SELL Signal'), row=1, col=1)
                
            if latest_active_sl and latest_active_tp:
                fig.add_hline(y=latest_active_tp, line_dash="dash", line_color="#00e5a0", annotation_text="Target Line", row=1, col=1)
                fig.add_hline(y=latest_active_sl, line_dash="dash", line_color="#ff4d6d", annotation_text="Stop Loss Line", row=1, col=1)
                
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['MACD_Line'], line=dict(color='#2196f3', width=1.5), name='MACD'), row=2, col=1)
            fig.add_trace(go.Scatter(x=df['Timestamp'], y=df['Signal_Line'], line=dict(color='#ff9800', width=1.5), name='Signal'), row=2, col=1)

            fig.update_layout(plot_bgcolor='white', paper_bgcolor='white', height=650, margin=dict(l=10, r=10, t=30, b=10), dragmode='pan', hovermode='x unified', showlegend=False)
            fig.update_xaxes(fixedrange=False, rangeslider_visible=False, tickformat="%H:%M")
            fig.update_yaxes(fixedrange=False)
            
            chart_config = {'scrollZoom': True, 'displayModeBar': True, 'displaylogo': False}
            st.plotly_chart(fig, use_container_width=True, config=chart_config)
            
            if auto_refresh:
                time.sleep(10)
                st.rerun()
        else:
            st.info("Market data is not available for today yet or it is a trading holiday.")
