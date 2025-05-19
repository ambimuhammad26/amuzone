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

PAIRS = ['XAUUSD', 'GBPJPY', 'EURUSD']

# ================= Helper Functions ===================
def send_signal(message, df):
    print("Kirim sinyal:", message)
    df.index = pd.to_datetime(df['datetime'])
    df_plot = df[['open', 'high', 'low', 'close']].copy()
    df_plot.columns = ['Open', 'High', 'Low', 'Close']
    chart_file = '/tmp/chart.png'
    mpf.plot(df_plot[-50:], type='candle', style='charles', volume=False, savefig=chart_file)
    with open(chart_file, 'rb') as photo:
        bot.send_photo(CHAT_ID, photo, caption=message)

def get_trend_h1(symbol):
    df_h1 = tv.get_hist(symbol=symbol, exchange='OANDA', interval=Interval.in_1_hour, n_bars=100)
    if df_h1 is None or df_h1.empty:
        return None
    df_h1['ema50'] = df_h1['close'].ewm(span=50).mean()
    trend = 'bullish' if df_h1['close'].iloc[-1] > df_h1['ema50'].iloc[-1] else 'bearish'
    return trend

def detect_liquidity_sweep(df):
    high_sweep = df['high'].iloc[-1] > df['high'].iloc[-2] and df['close'].iloc[-1] < df['open'].iloc[-1]
    low_sweep = df['low'].iloc[-1] < df['low'].iloc[-2] and df['close'].iloc[-1] > df['open'].iloc[-1]
    return 'bearish' if high_sweep else 'bullish' if low_sweep else None

def detect_fvg(df):
    try:
        fvg_up = df['low'].iloc[-3] > df['high'].iloc[-1]
        fvg_down = df['high'].iloc[-3] < df['low'].iloc[-1]
        if fvg_up:
            return (True, df['low'].iloc[-3])
        elif fvg_down:
            return (True, df['high'].iloc[-3])
        else:
            return (False, None)
    except:
        return (False, None)

def estimate_volatility(df):
    return df['high'].rolling(10).max().iloc[-1] - df['low'].rolling(10).min().iloc[-1]

def check_fundamentals(api_key):
    try:
        now = datetime.now(timezone.utc)
        today = now.strftime('%Y-%m-%d')
        url = f'https://financialmodelingprep.com/api/v3/economic_calendar?from={today}&to={today}&apikey={api_key}'
        res = requests.get(url)
        data = res.json()
        if not isinstance(data, list):
            print("⚠️ Unexpected response from fundamental API:", data)
            return True
        for event in data:
            if event.get('country') != 'US':
                continue
            if event.get('importance') == 'High':
                event_time_str = f"{event.get('date', today)} {event.get('time', '00:00:00')}"
                try:
                    event_time = datetime.strptime(event_time_str, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc)
                except:
                    continue
                if 0 <= (event_time - now).total_seconds() <= 3600:
                    print(f"⚠️ Upcoming High Impact US News: {event.get('event')} at {event.get('time')}")
                    return False
        return True
    except Exception as e:
        print("Fundamental check error:", e)
        return True

def is_trading_hours():
    now = datetime.now().time()
    return now.hour >= 8 and now.hour <= 22

def detect_market_structure(df):
    last_highs = df['high'].rolling(3).max()
    last_lows = df['low'].rolling(3).min()
    higher_high = last_highs.iloc[-1] > last_highs.iloc[-2]
    higher_low = last_lows.iloc[-1] > last_lows.iloc[-2]
    lower_high = last_highs.iloc[-1] < last_highs.iloc[-2]
    lower_low = last_lows.iloc[-1] < last_lows.iloc[-2]
    if higher_high and higher_low:
        return 'bullish'
    elif lower_high and lower_low:
        return 'bearish'
    else:
        return 'ranging'

# Fungsi tambahan: deteksi bullish / bearish engulfing candle terakhir
def is_engulfing(df):
    if len(df) < 2:
        return None
    prev = df.iloc[-2]
    last = df.iloc[-1]

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

# ================= Main Loop ===================
while True:
    try:
        if not is_trading_hours():
            print("⏸ Di luar jam trading aktif (08:00–22:00 WIB)")
            time.sleep(60)
            continue

        for symbol in PAIRS:
            trend_h1 = get_trend_h1(symbol)
            if trend_h1 is None:
                print(f"❌ Tidak bisa menentukan trend H1 untuk {symbol}")
                continue

            df = tv.get_hist(symbol=symbol, exchange='OANDA', interval=Interval.in_5_minute, n_bars=50)
            if df is None or df.empty:
                print(f"❌ Data kosong dari TradingView untuk {symbol}")
                continue

            sweep = detect_liquidity_sweep(df)
            if sweep != trend_h1:
                continue

            market_structure = detect_market_structure(df)
            if market_structure != trend_h1:
                continue

            # Cek pola engulfing candle terakhir
            engulfing = is_engulfing(df)
            if engulfing != sweep:
                continue

            fvg_ok, entry = detect_fvg(df)
            if not fvg_ok or entry is None:
                continue

            # Pastikan harga menyentuh FVG sebelum kirim sinyal
            if sweep == 'bullish' and not (df['low'].iloc[-1] <= entry <= df['high'].iloc[-1]):
                continue
            if sweep == 'bearish' and not (df['low'].iloc[-1] <= entry <= df['high'].iloc[-1]):
                continue

            if not check_fundamentals(FMP_API_KEY):
                print("⏸ Fundamental tidak mendukung — sinyal dibatalkan.")
                continue

            volatility = estimate_volatility(df)
            risk = volatility * 0.3
            rr = 3 if volatility < 2 else 2
            sl = entry - risk if sweep == 'bullish' else entry + risk
            tp = entry + risk * rr if sweep == 'bullish' else entry - risk * rr
            confidence = 90 if volatility < 2 else 80

            msg = f"""
{'🟢 BUY' if sweep == 'bullish' else '🔴 SELL'} {symbol} (SMC Scalping 5m)
📍 Entry (FVG): {entry:.2f}
🛑 SL: {sl:.2f}
🎯 TP: {tp:.2f} (RR ~1:{rr})
📊 Confidence: {confidence}%
🧠 Setup: Liquidity Sweep + FVG + Market Structure + Engulfing + Trend H1
🕐 Trend H1: {trend_h1.title()}
🌐 Data: OANDA via TradingView
📰 US News Checked ✅
            """
            send_signal(msg, df)
            time.sleep(2)

        time.sleep(60)

    except Exception as e:
        print("Error:", e)
        time.sleep(60)
