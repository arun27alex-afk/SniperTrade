import datetime
import time

import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
import pandas as pd
from fyers_apiv3 import fyersModel

from nifty_strategy import add_indicators, evaluate_signal, run_intraday_backtest, NO_TRADE_START, NO_TRADE_END

CLIENT_ID = "BT8FRQLN19-200"
SECRET_KEY = "0ivLeQN8vdI2VyKA"
REDIRECT_URI = "https://snipertrade-9sqhw3vstzhpvpnmyz4n5y.streamlit.app/"

st.set_page_config(page_title="Sniper Trade App - NIFTY 50", page_icon="🎯", layout="wide")


def play_alert_sound():
    st.components.v1.html('<audio autoplay="true"><source src="https://assets.mixkit.co/active_storage/sfx/2869/2869-preview.mp3" type="audio/mpeg"></audio>', width=0, height=0, scrolling=False)


def get_premium(fyers, expiry_str, atm_strike, opt_type):
    symbol = f"NSE:NIFTY{expiry_str}{atm_strike}{opt_type}"
    try:
        quote_res = fyers.quotes(data={"symbols": symbol})
        if quote_res.get("s") == "ok":
            return quote_res["d"][0]["v"]["lp"]
    except Exception as exc:
        st.caption(f"Premium quote unavailable: {exc}")
    return 0.0


st.title("🎯 Sniper Trade App (NIFTY 50 Live & Algo Execution)")
st.markdown("---")
st.info("Strategy upgraded: fewer, higher-probability trades only. The UI and Fyers flow are intentionally unchanged.")

with st.expander("Why this strategy is stricter"):
    st.markdown(
        """
        * **Trend stack + 15m confirmation** rejects counter-trend scalps and aligns 5-minute entries with the higher timeframe.
        * **ADX + DI filter** avoids weak/sideways sessions where EMA/VWAP signals usually fail.
        * **VWAP breakout/retest** replaces basic above/below VWAP logic, reducing late chase entries.
        * **Fresh MACD crossover + zero-line** requires new momentum, not stale MACD alignment.
        * **RSI slope and range limits** confirm momentum while avoiding overextended option-premium entries.
        * **Volume + ORB confirmation** requires participation and range expansion before buying CE/PE.
        * **ATR risk with 1:2.25 reward and trailing stop** preserves dynamic exits while keeping reward between 1:2 and 1:2.5.
        * **Duplicate and max-trade guards** cap signals at premium setups only.
        """
    )

if "access_token" not in st.session_state:
    st.session_state["access_token"] = None

query_params = st.query_params
if "auth_code" in query_params:
    session = fyersModel.SessionModel(client_id=CLIENT_ID, secret_key=SECRET_KEY, redirect_uri=REDIRECT_URI, response_type="code", grant_type="authorization_code")
    session.set_token(query_params["auth_code"])
    response = session.generate_token()
    if response.get("s") == "ok":
        st.session_state["access_token"] = response["access_token"]
        st.success("✅ Fyers Connected Successfully!")
    else:
        st.error("Login Failed. Please try again.")

if not st.session_state["access_token"]:
    st.subheader("🔑 Step 1: 1-Click Fyers Login")
    session = fyersModel.SessionModel(client_id=CLIENT_ID, redirect_uri=REDIRECT_URI, response_type="code", grant_type="authorization_code")
    st.markdown(f"**[👉 Click Here to Login to Fyers]({session.generate_authcode()})**")

if st.session_state["access_token"]:
    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, is_async=False, token=st.session_state["access_token"], log_path="")
    today = datetime.date.today()
    today_date = (today - datetime.timedelta(days=1 if today.weekday() == 5 else 2 if today.weekday() == 6 else 0)).strftime("%Y-%m-%d")
    res = fyers.history(data={"symbol": "NSE:NIFTY50-INDEX", "resolution": "5", "date_format": "1", "range_from": today_date, "range_to": today_date, "cont_flag": "1"})

    if res.get("s") == "ok" and res.get("candles"):
        df = pd.DataFrame(res["candles"], columns=["Timestamp", "Open", "High", "Low", "Close", "Volume"])
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], unit="s").dt.tz_localize("UTC").dt.tz_convert("Asia/Kolkata")
        df = add_indicators(df)
        stats, trades, active_trade = run_intraday_backtest(df)
        buy_x = [t["time"] for t in trades if t["side"] == "CE"]
        buy_y = [t["entry"] - 15 for t in trades if t["side"] == "CE"]
        sell_x = [t["time"] for t in trades if t["side"] == "PE"]
        sell_y = [t["entry"] + 15 for t in trades if t["side"] == "PE"]

        st.subheader("📊 Today's Auto-Backtest Scorecard")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Signals Triggered", stats["signals"])
        col2.metric("🎯 Targets Hit", stats["targets"])
        col3.metric("🛡️ Cost-to-Cost", stats["breakeven"])
        col4.metric("🛑 Stop Loss Hit", stats["stops"])
        closed = stats["targets"] + stats["stops"] + stats["breakeven"]
        col5.metric("🏆 Win Rate (%)", f"{(stats['targets'] / closed * 100) if closed else 0:.1f}%")
        st.markdown("---")

        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        close = latest["Close"]
        decision = evaluate_signal(df, len(df) - 1, trades[-1]["side"] if trades else None)

        with st.sidebar:
            st.header("📈 Live Market")
            st.metric(label="NIFTY 50 (Spot)", value=f"{close:,.2f}", delta=f"{close - prev['Close']:.2f}")
            st.markdown("---")
            st.subheader("⚙️ Options Settings")
            expiry_str = st.text_input("Enter Expiry (e.g., 26JUN)", "26JUN")
            num_lots = st.number_input("Select Number of Lots", min_value=1, max_value=50, value=1, step=1)
            total_qty = num_lots * 65
            st.write(f"Total Quantity: **{total_qty} shares**")
            st.markdown("---")
            auto_refresh = st.checkbox("🔄 Auto Refresh (10 Sec)", value=True)

        st.subheader("🎯 Live Signal Alert")
        atm_strike = int(round(close / 50) * 50)
        signal_time = latest["Timestamp"].strftime("%I:%M %p")
        if NO_TRADE_START <= latest["Timestamp"].time() <= NO_TRADE_END:
            st.warning("⏳ **NO TRADE ZONE (12:00 PM to 1:30 PM)**")
        elif decision.signal:
            play_alert_sound()
            premium = get_premium(fyers, expiry_str, atm_strike, decision.signal)
            opt_symbol = f"NSE:NIFTY{expiry_str}{atm_strike}{decision.signal}"
            alert = st.success if decision.signal == "CE" else st.error
            alert(f"### {'🟢 MARKET GOING UP - BUY CE' if decision.signal == 'CE' else '🔴 MARKET GOING DOWN - BUY PE'} (Score: {decision.score}/{len(decision.checklist)}) @ {signal_time}")
            st.markdown("### 📊 Institutional Checklist")
            for label, ok in decision.checklist.items():
                st.markdown(f"{'✅' if ok else '❌'} **{label}**")
            
            if premium > 0:
                # 🚀 NEW: PERCENTAGE-BASED TARGET AND STOP LOSS FOR PREMIUM
                target_pct = 0.20  # 20% Target
                sl_pct = 0.10      # 10% Stop Loss
                
                target_price = round(premium + (premium * target_pct), 2)
                sl_price = round(premium - (premium * sl_pct), 2)
                
                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("📌 Strike Rate", f"{atm_strike} {decision.signal}")
                c2.metric("🚪 Entry Price", f"₹{premium}")
                c3.metric(f"🎯 Target (+20%)", f"₹{target_price}")
                c4.metric(f"🛑 Stop Loss (-10%)", f"₹{sl_price}")
                c5.metric("⏰ Signal Time", signal_time)
                st.info(f"💡 **Safe Entry Range:** ₹{premium} to ₹{round(premium + 4, 2)} only. Avoid chasing beyond this range.")
                
                if st.button(f"🚀 BUY {atm_strike} {decision.signal} NOW ({num_lots} Lot)", type="primary", use_container_width=True):
                    order_data = {"symbol": opt_symbol, "qty": total_qty, "type": 2, "side": 1, "productType": "MARGIN", "limitPrice": 0, "stopPrice": 0, "validity": "DAY", "disclosedQty": 0, "offlineOrder": "False"}
                    order_res = fyers.place_order(data=order_data)
                    st.success(f"✅ Order Placed Successfully! ID: {order_res.get('id')}") if order_res.get("s") == "ok" else st.error(f"❌ Order Failed: {order_res.get('message')}")
            else:
                st.warning(f"Strike: {atm_strike} {decision.signal} - **Market Closed or Expiry Incorrect**")
        else:
            st.warning("### 🟡 WAITING FOR PERFECT SETUP")
            st.markdown(f"**{decision.reason}**\n\n* **Best Score:** {decision.score}/{len(decision.checklist)}")
            for label, ok in decision.checklist.items():
                st.markdown(f"{'✅' if ok else '❌'} {label}")

        st.markdown("---")
        st.subheader("🖥️ Live Market HUD")
        h1, h2, h3, h4 = st.columns(4)
        h1.info(f"**RSI (14):** {latest['RSI']:.2f}\n\n{'🟢 Momentum' if latest['RSI'] > 55 else '🔴 Momentum' if latest['RSI'] < 45 else '🟡 Neutral'}")
        h2.info(f"**ADX (14):** {latest['ADX']:.2f}\n\n{'🟢 Trending' if latest['ADX'] >= 22 else '🔴 Sideways'}")
        h3.info(f"**15m Trend:**\n\n{'🟢 Bullish' if latest['HTF_EMA_9'] > latest['HTF_EMA_21'] else '🔴 Bearish'}")
        h4.info(f"**VWAP Setup:**\n\nDistance {latest['VWAP_Distance_ATR']:.2f} ATR")

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.75, 0.25])
        fig.add_trace(go.Candlestick(x=df["Timestamp"], open=df["Open"], high=df["High"], low=df["Low"], close=df["Close"], name="Candles"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["VWAP"], line=dict(color="#795548", width=2, dash="dash"), name="VWAP"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["EMA_9"], line=dict(color="#2196f3", width=1.5), name="EMA 9"), row=1, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["EMA_21"], line=dict(color="#f44336", width=1.5), name="EMA 21"), row=1, col=1)
        fig.add_trace(go.Scatter(x=buy_x, y=buy_y, mode="markers", marker=dict(symbol="triangle-up", size=16, color="#00e5a0"), name="BUY CE"), row=1, col=1)
        fig.add_trace(go.Scatter(x=sell_x, y=sell_y, mode="markers", marker=dict(symbol="triangle-down", size=16, color="#ff4d6d"), name="BUY PE"), row=1, col=1)
        if active_trade:
            fig.add_hline(y=active_trade["target"], line_dash="dash", line_color="#00e5a0", annotation_text="Target", row=1, col=1)
            fig.add_hline(y=active_trade["sl"], line_dash="dash", line_color="#ff4d6d", annotation_text="Stop Loss", row=1, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["MACD_Line"], line=dict(color="#2196f3", width=1.5), name="MACD"), row=2, col=1)
        fig.add_trace(go.Scatter(x=df["Timestamp"], y=df["Signal_Line"], line=dict(color="#ff9800", width=1.5), name="Signal"), row=2, col=1)
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white", height=650, margin=dict(l=10, r=10, t=30, b=10), dragmode="pan", hovermode="x unified", showlegend=False)
        fig.update_xaxes(fixedrange=False, rangeslider_visible=False, tickformat="%H:%M")
        fig.update_yaxes(fixedrange=False)
        st.plotly_chart(fig, use_container_width=True, config={"scrollZoom": True, "displayModeBar": True, "displaylogo": False})
        if auto_refresh:
            time.sleep(10)
            st.rerun()
    else:
        st.info("Market data is not available for today yet or it is a trading holiday.")
