from tvDatafeed import TvDatafeed, Interval
import pandas as pd
import time
import telebot
import requests
from datetime import datetime, timezone
import os
import matplotlib.pyplot as plt
import mplfinance as mpf

# ===== Konfigurasi Telegram Bot & FMP API Key =====
API_TOKEN = '8101318218:AAFTBP-D827m3GI3QPFk7KjqIR4j6zU0g9k'
CHAT_ID = '7248790632'
FMP_API_KEY = 'WJjcggzQs1iTnWniHLKrvXqIsueD7L2i'

bot = telebot.TeleBot(API_TOKEN)

# ===== Inisialisasi TradingView Tanpa Login =====
tv = TvDatafeed()

# ===== Kirim sinyal ke Telegram =====
def send_signal(message, df):
    print("Kirim sinyal:", message)
    # Generate chart
    df.index = pd.to_datetime(df['datetime'])
    df_plot = df[['open', 'high', 'low', 'close']].copy()
    df_plot.columns = ['Open', 'High', 'Low', 'Close']
    chart_file = '/tmp/chart.png'
    mpf.plot(df_plot[-50:], type='candle', style='charles', volume=False, savefig=chart_file)
    with open(chart_file, 'rb') as photo:
        bot.send_photo(CHAT_ID, photo, caption=message)

# ===== Deteksi pola Engulfing =====
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

# ===== Deteksi Order Block =====
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

# ===== Deteksi Support & Resistance =====
def detect_support_resistance(df, tolerance=0.5):
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

# ===== Deteksi Supply & Demand Zones =====
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

# ===== Hitung RSI =====
def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)

    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

# ===== Hitung MACD =====
def calculate_macd(df):
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    return macd_line.iloc[-1], signal_line.iloc[-1]

# ===== Cek Fundamental News =====
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

# ===== Main Loop =====
while True:
    try:
        df = tv.get_hist(symbol='XAUUSD', exchange='OANDA', interval=Interval.in_5_minute, n_bars=50)
        if df is None or df.empty:
            print("❌ Data kosong dari TradingView")
            time.sleep(60)
            continue

        pattern = is_engulfing(df)

        if pattern:
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

            if pattern == 'bullish' and (rsi < 50 or macd < signal):
                print("📉 RSI atau MACD tidak mendukung bullish")
                time.sleep(60)
                continue
            elif pattern == 'bearish' and (rsi > 50 or macd > signal):
                print("📈 RSI atau MACD tidak mendukung bearish")
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

            msg = (
                f"{'🟢 BUY' if pattern == 'bullish' else '🔴 SELL'} XAU/USD (Scalping 5m)\n"
                f"📍 Entry: {entry:.2f}\n"
                f"🛑 SL: {sl:.2f}\n"
                f"🎯 TP: {tp:.2f}\n"
                f"📊 Pattern: {pattern.title()} Engulfing + Order Block\n"
                f"🌐 Data: OANDA via TradingView\n"
                f"📰 News Checked ✅"
                f"{sr_info}{sd_info}{rsi_info}{macd_info}"
            )
            send_signal(msg, df)

        time.sleep(300)  # 5 menit

    except Exception as e:
        print("Error:", e)
        time.sleep(60)
