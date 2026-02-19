import ccxt
import pandas as pd
import time
import requests
import os
import sys
import io
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

# ==========================================
# 운영체제 맞춤 설정 (교차 플랫폼 지원)
# ==========================================
IS_WINDOWS = sys.platform == 'win32'

if IS_WINDOWS:
    import msvcrt
    # 윈도우 인코딩 문제 해결 (이모지 출력 지원)
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
else:
    import fcntl

# ==========================================
# 1. 환경 설정 및 세팅
# ==========================================
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# 모니터링 설정
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'SOL/USDT']
TIMEFRAME = '5m'
SMA_PERIODS = [7, 25, 99]
INTERVAL_SECONDS = 60  # 정기 리포트 간격 (60초 = 1분)
SUPPORTED_TIMEFRAME = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d']
LOCK_FILE = "sma_monitor.lock"

# 타임프레임별 분 단위 변환
TIMEFRAME_MINUTES = {
    '1m': 1, '3m': 3, '5m': 5, '15m': 15, '30m': 30,
    '1h': 60, '2h': 120, '4h': 240, '6h': 360, '8h': 480, '12h': 720, '1d': 1440
}

# 번호별 배열 매핑
ALIGNMENT_MAP = {
    '1': '7>25>99',
    '2': '25>7>99',
    '3': '25>99>7',
    '4': '99>25>7',
    '5': '99>7>25',
    '6': '7>99>25'
}

# 상태 관리 변수
last_update_id = 0
last_report_time = datetime.min
is_report_enabled = True      # 정기 리포트 활성화 여부
target_alignment = None       # 알림을 받을 타겟 배열 (예: '7>25>99')
alert_sent_state = {symbol: False for symbol in SYMBOLS} # 코인별 알림 중복 방지
next_alert_time = None        # 다음 알람 체크 시각 (UTC)

# API 객체 초기화 (재사용)
exchange = ccxt.binance({'options': {'defaultType': 'future'}})

# ==========================================
# 2. 핵심 기능 함수
# ==========================================

def get_next_candle_close(timeframe):
    """현재 시각 기준으로 다음 봉 마감 시각(UTC)을 계산"""
    now_utc = datetime.now(timezone.utc)
    minutes = TIMEFRAME_MINUTES.get(timeframe, 5)
    
    # 현재 UTC 시각을 자정 기준 분으로 변환
    total_minutes = now_utc.hour * 60 + now_utc.minute
    
    # 다음 봉 마감 시각 계산 (올림)
    current_candle_start = (total_minutes // minutes) * minutes
    next_close = current_candle_start + minutes
    
    # 다음 마감 시각을 datetime으로 변환
    next_close_dt = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(minutes=next_close)
    
    # 만약 계산된 시각이 다음 날로 넘어가면 처리
    if next_close >= 1440:
        next_close_dt = now_utc.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1, minutes=next_close - 1440)
    
    # 10초 버퍼 추가 (데이터 확정 대기)
    next_close_dt += timedelta(seconds=10)
    
    return next_close_dt

def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    if not TOKEN or not CHAT_ID:
        print("Telegram Token or Chat ID not found.")
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {'chat_id': CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
    try:
        # 이모지 포함 메시지 처리 시 윈도우/리눅스 공통으로 requests는 내부적으로 utf-8 처리함
        response = requests.post(url, json=payload, timeout=10)
        res_json = response.json()
        if not res_json.get('ok'):
            print(f"❌ Telegram Error: {res_json.get('description')} | Message: {message[:30]}...")
        else:
            print(f"✅ Message sent successfully: {message[:30]}...")
    except Exception as e:
        print(f"Error sending message: {e}")

# 전역 변수 추가
get_updates_call_count = 0

def get_updates():
    """텔레그램 명령어 수신 및 처리"""
    global last_update_id, TIMEFRAME, is_report_enabled, target_alignment
    global alert_sent_state, get_updates_call_count, INTERVAL_SECONDS, next_alert_time
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    
    get_updates_call_count += 1
    # 20회마다 폴링 상태 로그 출력 (너무 잦은 로그 방지)
    if get_updates_call_count % 20 == 0:
        print(f"DEBUG: get_updates loop #{get_updates_call_count}...", flush=True)

    offset = last_update_id + 1 if last_update_id > 0 else 0 
    params = {'offset': offset, 'timeout': 5}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        res_json = response.json()
        updates = res_json.get('result', [])
        
        for update in updates:
            last_update_id = update['update_id']
            
            if 'message' in update:
                chat_id = str(update['message']['chat']['id'])
                
                if chat_id != str(CHAT_ID):
                    print(f"Ignored message from unknown chat_id: {chat_id}")
                    continue
                
                if 'text' in update['message']:
                    raw_cmd = update['message']['text'].strip().lower()
                    raw_cmd = " ".join(raw_cmd.split())
                    
                    print(f"📩 Received command: {raw_cmd}", flush=True)

                    # 명령어 분기
                    if raw_cmd in SUPPORTED_TIMEFRAME:
                        TIMEFRAME = raw_cmd
                        next_alert_time = get_next_candle_close(raw_cmd)
                        kst_time = next_alert_time + timedelta(hours=9)
                        send_telegram_message(f"✅ 타임프레임이 *{raw_cmd}*로 변경되었습니다.\n🕒 다음 알람 체크: {kst_time.strftime('%H:%M:%S')} (KST)")
                    
                    elif raw_cmd == 'report on':
                        is_report_enabled = True
                        send_telegram_message("✅ 정기 리포트가 *활성화*되었습니다.")
                    
                    elif raw_cmd == 'report off':
                        is_report_enabled = False
                        send_telegram_message("✅ 정기 리포트가 *비활성화*되었습니다.")
                    
                    elif raw_cmd.startswith('interval '):
                        try:
                            new_interval = int(raw_cmd.replace('interval ', '').strip())
                            if 10 <= new_interval <= 3600:
                                INTERVAL_SECONDS = new_interval
                                send_telegram_message(f"✅ 리포트 간격이 *{new_interval}초* ({new_interval//60}분)로 변경되었습니다.")
                            else:
                                send_telegram_message("❌ 간격은 10초에서 3600초(60분) 사이여야 합니다.")
                        except ValueError:
                            send_telegram_message("❌ 올바른 숫자를 입력하세요. 예: `interval 60`")
                    
                    elif raw_cmd.startswith('alert '):
                        target = raw_cmd.replace('alert ', '').strip()
                        if target in ALIGNMENT_MAP: target = ALIGNMENT_MAP[target]
                        
                        if target in ALIGNMENT_MAP.values():
                            target_alignment = target
                            alert_sent_state = {symbol: False for symbol in SYMBOLS}
                            next_alert_time = get_next_candle_close(TIMEFRAME)
                            kst_time = next_alert_time + timedelta(hours=9)
                            send_telegram_message(f"🎯 알람 타겟이 *{target}*로 설정되었습니다.\n🕒 다음 체크: {kst_time.strftime('%H:%M:%S')} (KST)")
                        elif target == 'off':
                            target_alignment = None
                            next_alert_time = None
                            send_telegram_message("🚫 타겟 알람이 해제되었습니다.")
                        else:
                            send_telegram_message("❓ 지원하지 않는 옵션입니다.")
 
                    elif raw_cmd == 'now':
                        send_report(is_manual=True)
                    
                    elif raw_cmd == 'status':
                        interval_min = INTERVAL_SECONDS // 60
                        interval_sec = INTERVAL_SECONDS % 60
                        interval_str = f"{interval_min}분 {interval_sec}초" if interval_sec else f"{interval_min}분"
                        report_status = f"✅ ON ({interval_str} 주기)" if is_report_enabled else "❌ OFF"
                        alert_status = f"🔔 ON ({target_alignment})" if target_alignment else "🔕 OFF"
                        # 다음 알람 체크 시각 표시
                        if next_alert_time and target_alignment:
                            kst_time = next_alert_time + timedelta(hours=9)
                            next_check_str = kst_time.strftime('%H:%M:%S')
                        else:
                            next_check_str = "설정 안됨"
                        msg = "⚙️ *모니터링 설정 현황*\n\n" \
                              f"• 타임프레임: `{TIMEFRAME}`\n" \
                              f"• 정기 리포트: `{report_status}`\n" \
                              f"• 지정 타겟 알람: `{alert_status}`\n" \
                              f"• 다음 알람 체크: `{next_check_str} (KST)`"
                        send_telegram_message(msg)
 
                    elif raw_cmd in ['help', '/start']:
                        timeframes_str = ", ".join(SUPPORTED_TIMEFRAME)
                        align_list = "\n".join([f"  {k}: {v}" for k, v in ALIGNMENT_MAP.items()])
                        msg = f"🤖 *SMA 모니터 명령어 가이드*\n\n" \
                              f"📊 *리포트 설정*\n" \
                              f"• `report on/off`: 리포트 켜기/끄기\n" \
                              f"• `interval [초]`: 리포트 간격 설정 (예: `interval 60`)\n\n" \
                              f"🎯 *타겟 알림*\n" \
                              f"• `alert [번호]`: 특정 배열 시 알람 설정\n{align_list}\n" \
                              f"• `alert off`: 알람 해제\n\n" \
                              f"⚙️ *기타 명령어*\n" \
                              f"• `status`: 현재 설정 확인\n" \
                              f"• `now`: 즉시 상황 보고\n\n" \
                              f"🕒 *타임프레임 변경*\n" \
                              f"• 명령어 입력: `{timeframes_str}` 중 하나 입력\n" \
                              f"  (예: `15m` 또는 `1h` 입력 시 즉시 변경)"
                        send_telegram_message(msg)
                    
                    else:
                        send_telegram_message("❓ 인식할 수 없는 명령어입니다. 'help'를 입력해 사용 가능한 명령어를 확인하세요.")
                else:
                    print("DEBUG: Received non-text message", flush=True)
                    
    except Exception as e:
        print(f"Error getting updates: {e}", flush=True)

def fetch_data(symbol):
    """바이낸스 데이터 가져오기"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=150)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"Error fetching data ({symbol}): {e}")
        return None

def calculate_smas(df):
    """SMA 지표 계산"""
    for period in SMA_PERIODS:
        df[f'sma_{period}'] = df['close'].rolling(window=period).mean()
    return df

def get_sma_info(df):
    """현재 SMA 배열 상태 파악"""
    if len(df) < max(SMA_PERIODS):
        return "데이터 부족", ""
    
    last_row = df.iloc[-1]
    s7 = last_row['sma_7']
    s25 = last_row['sma_25']
    s99 = last_row['sma_99']
    
    items = sorted([('7', s7), ('25', s25), ('99', s99)], key=lambda x: x[1], reverse=True)
    raw_alignment = ">".join([x[0] for x in items])
    
    # 표시용 (수렴 감지)
    order_str = items[0][0]
    for i in range(1, len(items)):
        prev_val = items[i-1][1]
        curr_val = items[i][1]
        diff_percent = abs(prev_val - curr_val) / ((prev_val + curr_val) / 2) * 100
        sep = " = " if diff_percent < 0.001 else " > "
        order_str += sep + items[i][0]
    
    if raw_alignment == '7>25>99':
        return f"🚀 *{order_str} (정배열)*", raw_alignment
    elif raw_alignment == '99>25>7':
        return f"📉 *{order_str} (역배열)*", raw_alignment
    else:
        return f"🔄 {order_str}", raw_alignment

def send_report(is_manual=False):
    """현재 상태 리포트 발송"""
    global last_report_time
    title = "📊 *수동 현황 보고*" if is_manual else f"📊 *정기 리포트 ({TIMEFRAME})*"
    report_lines = [title]
    
    for symbol in SYMBOLS:
        df = fetch_data(symbol)
        if df is not None:
            df = calculate_smas(df)
            status_str, _ = get_sma_info(df)
            report_lines.append(f"• {symbol}: {status_str}")
        else:
            report_lines.append(f"• {symbol}: 데이터 오류")
        time.sleep(0.5)
    
    send_telegram_message("\n".join(report_lines))
    if not is_manual:
        last_report_time = datetime.now()

def check_target_alerts():
    """지정된 타겟 배열 진입 여부 체크"""
    global alert_sent_state
    if not target_alignment:
        return

    for symbol in SYMBOLS:
        df = fetch_data(symbol)
        if df is not None:
            df = calculate_smas(df)
            status_str, current_alignment = get_sma_info(df)
            
            if current_alignment == target_alignment:
                if not alert_sent_state[symbol]:
                    msg = f"🎯 *[타겟 알람] 조건 충족!* 🔔\n품목: {symbol}\n배열: {status_str}\n봉: {TIMEFRAME}"
                    send_telegram_message(msg)
                    alert_sent_state[symbol] = True
            else:
                alert_sent_state[symbol] = False # 조건 벗어나면 초기화
        time.sleep(0.5)

# ==========================================
# 3. 메인 루프
# ==========================================

def check_single_instance():
    """하나의 인스턴스만 실행되도록 보장 (파일 잠금 활용)"""
    try:
        f = open(LOCK_FILE, "w")
        if IS_WINDOWS:
            # Windows: msvcrt.locking
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            # Unix/macOS: fcntl.lockf
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except (IOError, OSError):
        print("\n❌ [오류] 이미 프로그램이 실행 중입니다. 중복 실행을 차단합니다.")
        return None

def monitor():
    # 인스턴스 중복 체크
    lock_f = check_single_instance()
    if lock_f is None:
        sys.exit(1)
    global last_report_time
    start_msg = f"🔔 *모니터링 시스템 가동*\n대상: {', '.join(SYMBOLS)}\n기본봉: {TIMEFRAME}\n\nType 'help' for commands!"
    print(start_msg)
    send_telegram_message(start_msg)
    
    while True:
        try:
            # 1. 명령어 체크 (사용자로부터 수신)
            get_updates()
            
            # 2. 지정 알람 체크 (봉 마감 시점에만)
            if target_alignment and next_alert_time:
                now_utc = datetime.now(timezone.utc)
                if now_utc >= next_alert_time:
                    kst_time = next_alert_time + timedelta(hours=9)
                    print(f"🔔 봉 마감 감지! ({TIMEFRAME}) 알람 체크 중... (KST {kst_time.strftime('%H:%M:%S')})", flush=True)
                    check_target_alerts()
                    # 다음 봉 마감 시각으로 갱신
                    next_alert_time = get_next_candle_close(TIMEFRAME)
                    kst_next = next_alert_time + timedelta(hours=9)
                    print(f"⏭️ 다음 알람 체크: KST {kst_next.strftime('%H:%M:%S')}", flush=True)
            
            # 3. 정기 리포트 발송
            if is_report_enabled:
                if (datetime.now() - last_report_time).total_seconds() >= INTERVAL_SECONDS:
                    send_report()
            
            time.sleep(1)
            
        except KeyboardInterrupt:
            send_telegram_message("🛑 *시스템 종료*")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor()
