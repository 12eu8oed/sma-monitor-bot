import ccxt
import pandas as pd
import config

# API 객체 초기화 (재사용)
exchange = ccxt.binance({'options': {'defaultType': 'future'}})

def fetch_data(symbol):
    """바이낸스 데이터 가져오기"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=config.TIMEFRAME, limit=150)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching data ({symbol}): {e}")
        return None

def calculate_smas(df):
    """지정된 기간의 SMA 계산"""
    for period in config.SMA_PERIODS:
        df[f'SMA_{period}'] = df['close'].rolling(window=period).mean()
    return df

def get_sma_info(df):
    """현재 SMA 상태 조회 및 포맷팅"""
    last_row = df.iloc[-1]
    
    # SMA 값 가져오기
    sma_values = {p: last_row[f'SMA_{p}'] for p in config.SMA_PERIODS}
    
    # 정렬하여 순서 파악 (큰 값부터 작은 값 순)
    sorted_smas = sorted(sma_values.items(), key=lambda x: x[1], reverse=True)
    raw_alignment = ">".join(str(p) for p, v in sorted_smas)
    
    # 포맷 구성
    order_str = " > ".join(f"SMA{p}({v:,.2f})" for p, v in sorted_smas)
    
    # 정배열/역배열 표시
    if raw_alignment == '7>25>99':
        return f"🚀 *{order_str} (정배열)*", raw_alignment
    elif raw_alignment == '99>25>7':
        return f"📉 *{order_str} (역배열)*", raw_alignment
    else:
        return f"🔄 {order_str}", raw_alignment
