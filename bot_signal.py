from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import time
import telebot
import requests
from datetime import datetime, timezone
import os
import matplotlib.pyplot as plt
import mplfinance as mpf

API_TOKEN = '8101318218:AAFTBP-D827m3GI3QPFk7KjqIR4j6zU0g9k'
CHAT_ID = '7248790632'
FMP_API_KEY = 'WJjcggzQs1iTnWniHLKrvXqIsueD7L2i'

username = 'ambimuhammad'
password = 'PamulangMeruyung2!'

bot = telebot.TeleBot(API_TOKEN)
tv = TvDatafeed(username, password)

def send_signal(message, df):
    print("Kirim sinyal:", message)
    df.index = pd.to_datetime(df['datetime'])
    df_plot = df[['open', 'high', 'low', 'close']].copy()
    df_plot.columns = ['Open', 'High', 'Low', 'Close']
    chart_file = '/tmp/chart.png'
    mpf.plot(df_plot[-50:], type='candle', style='charles', volume=False, savefig=chart_file)
    with open(chart_file, 'rb') as photo:
        bot.send_photo(CHAT_ID, photo, caption=message)

def is_engulfing(df):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    bullish = (
        prev['close'] < prev['open'] and
        last['close'] > last['open'] and
        last['open'] < prev['close'] and
        last['close'] > prev['open']
    )
    bearish = (
        prev['close'] > prev['open'] and
        last['close'] < last['open'] and
        last['open'] > prev['close'] and
        last['close'] < prev['open']
    )
    return 'bullish' if bullish else 'bearish' if bearish else None

def detect_order_block(df, bullish=True):
    try:
        if bullish:
            return (
                df['close'].iloc[-4] < df['open'].iloc[-4] and
                df['close'].iloc[-3] > df['open'].iloc[-3] and
                df['close'].iloc[-2] > df['open'].iloc[-2]
            )
        else:
            return (
                df['close'].iloc[-4] > df['open'].iloc[-4] and
                df['close'].iloc[-3] < df['open'].iloc[-3] and
                df['close'].iloc[-2] < df['open'].iloc[-2]
            )
    except:
        return False

def detect_structure_change(df):
    last_high = df['high'].iloc[-2]
    last_low = df['low'].iloc[-2]
    current_high = df['high'].iloc[-1]
    current_low = df['low'].iloc[-1]
    prev_trend = df['close'].iloc[-3] < df['close'].iloc[-2]
    curr_trend = df['close'].iloc[-2] < df['close'].iloc[-1]
    if prev_trend and current_low < last_low:
        return 'CHOCH Bearish'
    elif not prev_trend and current_high > last_high:
        return 'CHOCH Bullish'
    return None

def detect_fvg(df):
    fvg_zones = []
    for i in range(2, len(df)):
        if df['low'].iloc[i] > df['high'].iloc[i-2]:
            fvg_zones.append(('bullish', df['high'].iloc[i-2], df['low'].iloc[i]))
        elif df['high'].iloc[i] < df['low'].iloc[i-2]:
            fvg_zones.append(('bearish', df['low'].iloc[i-2], df['high'].iloc[i]))
    return fvg_zones[-1] if fvg_zones else None

def detect_support_resistance(df):
    support = []
    resistance = []
    closes = df['close']
    highs = df['high']
    lows = df['low']
    for i in range(2, len(df)-2):
        if lows[i] < lows[i-1] and lows[i] < lows[i+1] and lows[i+1] < lows[i+2] and lows[i-1] < lows[i-2]:
            support.append(lows[i])
        if highs[i] > highs[i-1] and highs[i] > highs[i+1] and highs[i+1] > highs[i+2] and highs[i-1] > highs[i-2]:
            resistance.append(highs[i])
    last_price = closes.iloc[-1]
    nearest_support = min(support, key=lambda x: abs(x - last_price)) if support else None
    nearest_resistance = min(resistance, key=lambda x: abs(x - last_price)) if resistance else None
    return nearest_support, nearest_resistance

def detect_supply_demand(df):
    supply_zones = []
    demand_zones = []
    highs = df['high']
    lows = df['low']
    for i in range(2, len(df) - 2):
        if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
            supply_zones.append(highs[i])
        if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
            demand_zones.append(lows[i])
    last_price = df['close'].iloc[-1]
    nearest_supply = min(supply_zones, key=lambda x: abs(x - last_price)) if supply_zones else None
    nearest_demand = min(demand_zones, key=lambda x: abs(x - last_price)) if demand_zones else None
    return nearest_supply, nearest_demand

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def calculate_macd(df):
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1]

def check_fundamentals(api_key):
    try:
        now = datetime.now(timezone.utc)
        today = now.strftime('%Y-%m-%d')
        url = f'https://financialmodelingprep.com/api/v3/economic_calendar?from={today}&to={today}&apikey={api_key}'
        res = requests.get(url)
        data = res.json()
        for event in data:
            if event.get('importance') == 'High':
                event_time_str = f"{event.get('date', today)} {event.get('time', '00:00:00')}"
                try:
                    event_time = datetime.strptime(event_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                except:
                    continue
                if 0 <= (event_time - now).total_seconds() <= 3600:
                    print(f"⚠️ Upcoming High Impact News: {event.get('event')} at {event.get('time')}")
                    return False
        return True
    except Exception as e:
        print("Fundamental check error:", e)
        return True

def calculate_confidence(structure, fvg, pattern, rsi, macd, signal):
    score = 0
    if structure: score += 1
    if fvg: score += 1
    if pattern: score += 1
    if (pattern == 'bullish' and rsi > 50 and macd > signal) or (pattern == 'bearish' and rsi < 50 and macd < signal):
        score += 1
    return score

while True:
    try:
        df = tv.get_hist(symbol='XAUUSD', exchange='OANDA', interval=Interval.in_5_minute, n_bars=50)
        if df is None or df.empty:
            print("❌ Data kosong dari TradingView")
            time.sleep(60)
            continue

        structure = detect_structure_change(df)
        fvg = detect_fvg(df)
        pattern = is_engulfing(df)

        if not structure or not fvg or not pattern:
            print("❌ Struktur/Pattern/FVG tidak valid")
            time.sleep(60)
            continue

        if not check_fundamentals(FMP_API_KEY):
            print("⏸ Fundamental tidak mendukung — sinyal dibatalkan.")
            time.sleep(60)
            continue

        if pattern == 'bullish' and not detect_order_block(df, bullish=True):
            print("❌ Tidak ada bullish order block")
            time.sleep(60)
            continue
        elif pattern == 'bearish' and not detect_order_block(df, bullish=False):
            print("❌ Tidak ada bearish order block")
            time.sleep(60)
            continue

        rsi = calculate_rsi(df)
        macd, signal = calculate_macd(df)

        confidence = calculate_confidence(structure, fvg, pattern, rsi, macd, signal)
        if confidence < 4:
            print(f"⚠️ Confidence rendah: {confidence}/4")
            time.sleep(60)
            continue

        entry = df['close'].iloc[-1]
        sl = entry - 3 if pattern == 'bullish' else entry + 3
        tp = entry + 5 if pattern == 'bullish' else entry - 5

        support, resistance = detect_support_resistance(df)
        nearest_supply, nearest_demand = detect_supply_demand(df)

        sr_info = f"\n📉 Support: {support:.2f} | 📈 Resistance: {resistance:.2f}" if support and resistance else ""
        sd_info = f"\n🏬 Demand Zone: {nearest_demand:.2f} | 🏢 Supply Zone: {nearest_supply:.2f}" if nearest_demand and nearest_supply else ""
        rsi_info = f"\n📈 RSI: {rsi:.2f}"
        macd_info = f"\n📊 MACD: {macd:.2f} | Signal: {signal:.2f}"
        fvg_info = f"\n🪟 FVG Zone: {fvg[1]:.2f} - {fvg[2]:.2f}" if fvg else ""
        structure_info = f"\n📐 Structure: {structure}" if structure else ""
        confidence_info = f"\n✅ Confidence: {confidence}/4"

        msg = (
            f"{'🟢 BUY' if pattern == 'bullish' else '🔴 SELL'} XAU/USD (SMC Scalping 5m)\n"
            f"📍 Entry: {entry:.2f}\n"
            f"🛑 SL: {sl:.2f}\n"
            f"🎯 TP: {tp:.2f}\n"
            f"📊 Pattern: {pattern.title()} Engulfing + OB + BOS/FVG\n"
            f"🌐 Data: OANDA via TradingView\n"
            f"📰 News Checked ✅"
            f"{sr_info}{sd_info}{rsi_info}{macd_info}{structure_info}{fvg_info}{confidence_info}"
        )

        send_signal(msg, df)
        time.sleep(300)

    except Exception as e:
        print("Error:", e)
        time.sleep(60)