import time
from datetime import datetime, timedelta, timezone
import sys

import config
from utils import setup_os_environment, check_single_instance, get_next_candle_close
from market import fetch_data, calculate_smas, get_sma_info
from telegram_bot import send_telegram_message, get_updates

def send_report(is_manual=False):
    """현재 상태 리포트 발송"""
    title = "📊 *수동 현황 보고*" if is_manual else f"📊 *정기 리포트 ({config.TIMEFRAME})*"
    report_lines = [title]
    
    for symbol in config.SYMBOLS:
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
        config.last_report_time = datetime.now()

def check_target_alerts():
    """지정된 타겟 배열 진입 여부 체크"""
    if not config.target_alignment:
        return

    for symbol in config.SYMBOLS:
        df = fetch_data(symbol)
        if df is not None:
            df = calculate_smas(df)
            status_str, current_alignment = get_sma_info(df)
            
            if current_alignment == config.target_alignment:
                if not config.alert_sent_state[symbol]:
                    msg = f"🎯 *[타겟 알람] 조건 충족!* 🔔\n품목: {symbol}\n배열: {status_str}\n봉: {config.TIMEFRAME}"
                    send_telegram_message(msg)
                    config.alert_sent_state[symbol] = True
            else:
                config.alert_sent_state[symbol] = False # 조건 벗어나면 초기화
        time.sleep(0.5)

def check_trendline_alerts():
    """지정된 대각선 추세선 돌파 여부 체크"""
    if not config.active_trendlines:
        return
        
    now_utc = datetime.now(timezone.utc)
    current_timestamp = now_utc.timestamp()
    
    symbols_to_delete = []

    for symbol, t_data in config.active_trendlines.items():
        df = fetch_data(symbol)
        if df is not None and not df.empty:
            current_close = df.iloc[-1]['close']
            
            t1, p1 = t_data['t1'], t_data['p1']
            t2, p2 = t_data['t2'], t_data['p2']
            direction = t_data['direction']
            
            if t2 == t1: # prevent division by zero
                continue
                
            m = (p2 - p1) / (t2 - t1)
            b = p1 - m * t1
            
            trend_price = m * current_timestamp + b
            
            is_breakout = False
            if direction == 'up' and current_close > trend_price:
                is_breakout = True
            elif direction == 'down' and current_close < trend_price:
                is_breakout = True
                
            if is_breakout:
                msg = f"📈 *[추세선 돌파 알람] 조건 충족!* 🔔\n품목: {symbol}\n현재가: ${current_close:,.2f}\n기준선가격: ${trend_price:,.2f}\n방향: {direction} 이탈"
                send_telegram_message(msg)
                symbols_to_delete.append(symbol)
                
        time.sleep(0.5)
        
    for sym in symbols_to_delete:
        del config.active_trendlines[sym]

# ==========================================
# 메인 루프
# ==========================================

def monitor():
    setup_os_environment()
    
    # 인스턴스 중복 체크
    lock_f = check_single_instance()
    if lock_f is None:
        sys.exit(1)
        
    start_msg = f"🔔 *모니터링 시스템 가동*\n대상: {', '.join(config.SYMBOLS)}\n기본봉: {config.TIMEFRAME}\n\nType 'help' for commands!"
    print(start_msg)
    send_telegram_message(start_msg)
    
    while True:
        try:
            # 1. 명령어 체크 (사용자로부터 수신)
            trigger_now_report = get_updates()
            if trigger_now_report:
                send_report(is_manual=True)
            
            # 2. 지정 알람 체크 (봉 마감 시점에만)
            if (config.target_alignment or config.active_trendlines) and config.next_alert_time:
                now_utc = datetime.now(timezone.utc)
                if now_utc >= config.next_alert_time:
                    kst_time = config.next_alert_time + timedelta(hours=9)
                    print(f"🔔 봉 마감 감지! ({config.TIMEFRAME}) 알람 체크 중... (KST {kst_time.strftime('%H:%M:%S')})", flush=True)
                    check_target_alerts()
                    check_trendline_alerts()
                    # 다음 봉 마감 시각으로 갱신
                    config.next_alert_time = get_next_candle_close(config.TIMEFRAME)
                    kst_next = config.next_alert_time + timedelta(hours=9)
                    print(f"⏭️ 다음 알람 체크: KST {kst_next.strftime('%H:%M:%S')}", flush=True)
            
            # 3. 정기 리포트 발송
            if config.is_report_enabled:
                if (datetime.now() - config.last_report_time).total_seconds() >= config.INTERVAL_SECONDS:
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
