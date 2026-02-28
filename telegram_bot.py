import requests
from datetime import datetime, timedelta, timezone
import config
from utils import get_next_candle_close

def send_telegram_message(message):
    """텔레그램 메시지 전송"""
    if not config.TOKEN or not config.CHAT_ID:
        print("Telegram Token or Chat ID not found.")
        return
    url = f"https://api.telegram.org/bot{config.TOKEN}/sendMessage"
    payload = {'chat_id': config.CHAT_ID, 'text': message, 'parse_mode': 'Markdown'}
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

def get_updates():
    """텔레그램 명령어 수신 및 처리"""
    url = f"https://api.telegram.org/bot{config.TOKEN}/getUpdates"
    
    config.get_updates_call_count += 1
    # 20회마다 폴링 상태 로그 출력 (너무 잦은 로그 방지)
    if config.get_updates_call_count % 20 == 0:
        print(f"DEBUG: get_updates loop #{config.get_updates_call_count}...", flush=True)

    offset = config.last_update_id + 1 if config.last_update_id > 0 else 0 
    params = {'offset': offset, 'timeout': 5}
    
    # `now` 명령어 발생 시 외부에서 상태 보고를 트리거하기 위함
    trigger_now_report = False
    
    try:
        response = requests.get(url, params=params, timeout=10)
        res_json = response.json()
        updates = res_json.get('result', [])
        
        for update in updates:
            config.last_update_id = update['update_id']
            
            if 'message' in update:
                chat_id = str(update['message']['chat']['id'])
                
                if chat_id != str(config.CHAT_ID):
                    print(f"Ignored message from unknown chat_id: {chat_id}")
                    continue
                
                if 'text' in update['message']:
                    raw_cmd = update['message']['text'].strip().lower()
                    raw_cmd = " ".join(raw_cmd.split())
                    
                    print(f"📩 Received command: {raw_cmd}", flush=True)

                    # 명령어 분기
                    if raw_cmd in config.SUPPORTED_TIMEFRAME:
                        config.TIMEFRAME = raw_cmd
                        config.next_alert_time = get_next_candle_close(raw_cmd)
                        kst_time = config.next_alert_time + timedelta(hours=9)
                        send_telegram_message(f"✅ 타임프레임이 *{raw_cmd}*로 변경되었습니다.\n🕒 다음 알람 체크: {kst_time.strftime('%H:%M:%S')} (KST)")
                    
                    elif raw_cmd == 'report on':
                        config.is_report_enabled = True
                        send_telegram_message("✅ 정기 리포트가 *활성화*되었습니다.")
                    
                    elif raw_cmd == 'report off':
                        config.is_report_enabled = False
                        send_telegram_message("✅ 정기 리포트가 *비활성화*되었습니다.")
                    
                    elif raw_cmd.startswith('interval '):
                        try:
                            interval_val = int(raw_cmd.split()[1])
                            if 10 <= interval_val <= 3600:
                                config.INTERVAL_SECONDS = interval_val
                                send_telegram_message(f"✅ 리포트 간격이 *{interval_val}초*로 변경되었습니다.")
                            else:
                                send_telegram_message("❌ 간격은 10초에서 3600초(60분) 사이여야 합니다.")
                        except ValueError:
                            send_telegram_message("❌ 올바른 숫자를 입력하세요. 예: `interval 60`")
                    
                    elif raw_cmd.startswith('alert '):
                        target = raw_cmd.replace('alert ', '').strip()
                        if target in config.ALIGNMENT_MAP: target = config.ALIGNMENT_MAP[target]
                        
                        if target in config.ALIGNMENT_MAP.values():
                            config.target_alignment = target
                            config.alert_sent_state = {symbol: False for symbol in config.SYMBOLS}
                            config.next_alert_time = get_next_candle_close(config.TIMEFRAME)
                            kst_time = config.next_alert_time + timedelta(hours=9)
                            send_telegram_message(f"🎯 알람 타겟이 *{target}*로 설정되었습니다.\n🕒 다음 체크: {kst_time.strftime('%H:%M:%S')} (KST)")
                        elif target == 'off':
                            config.target_alignment = None
                            config.next_alert_time = None
                            send_telegram_message("🚫 타겟 알람이 해제되었습니다.")
                        else:
                            send_telegram_message("❓ 지원하지 않는 옵션입니다.")

                    elif raw_cmd.startswith('trend '):
                        parts = raw_cmd.split()
                        try:
                            if len(parts) == 9:
                                _, coin, d1, t1, p1, d2, t2, p2, direction = parts
                                curr_year = datetime.now().year
                                # Parse to UTC timestamp Assuming KST input (UTC+9)
                                dt1_str = f"{curr_year}/{d1} {t1}"
                                dt2_str = f"{curr_year}/{d2} {t2}"
                                dt1 = datetime.strptime(dt1_str, "%Y/%m/%d %H:%M") - timedelta(hours=9)
                                dt2 = datetime.strptime(dt2_str, "%Y/%m/%d %H:%M") - timedelta(hours=9)
                                p1, p2 = float(p1), float(p2)
                                
                                if dt1 >= dt2:
                                    send_telegram_message("❌ 두 번째 꺾이는 점의 시간이 첫 번째보다 느려야 합니다.")
                                    continue
                                if direction not in ['up', 'down']:
                                    send_telegram_message("❌ 방향은 up 또는 down 이어야 합니다.")
                                    continue
                                
                                symbol_key = [s for s in config.SYMBOLS if coin.upper() in s]
                                if symbol_key:
                                    symbol = symbol_key[0]
                                    config.active_trendlines[symbol] = {
                                        't1': dt1.replace(tzinfo=timezone.utc).timestamp(), 'p1': p1,
                                        't2': dt2.replace(tzinfo=timezone.utc).timestamp(), 'p2': p2,
                                        'direction': direction
                                    }
                                    send_telegram_message(f"📈 *추세선 알람 설정 완료* ({symbol})\n점1: {d1} {t1} (${p1})\n점2: {d2} {t2} (${p2})\n조건: {direction} (종가 기준돌파)")
                                else:
                                    send_telegram_message("❌ 지원하지 않는 코인입니다.")
                                    
                            elif len(parts) == 3 and parts[1] == 'off':
                                coin = parts[2]
                                symbol_key = [s for s in config.SYMBOLS if coin.upper() in s]
                                if symbol_key:
                                    symbol = symbol_key[0]
                                    if symbol in config.active_trendlines:
                                        del config.active_trendlines[symbol]
                                        send_telegram_message(f"🚫 {symbol} 추세선 알람이 해제되었습니다.")
                                    else:
                                        send_telegram_message(f"❓ {symbol}에 설정된 추세선이 없습니다.")
                                else:
                                    send_telegram_message("❌ 지원하지 않는 코인입니다.")
                            else:
                                send_telegram_message("❓ 형식 오류!\n설정: `trend btc 02/24 09:00 90000 02/25 09:00 95000 up`\n해제: `trend off btc`")
                        except ValueError:
                            send_telegram_message("❌ 형식 오류! 형식에 맞게 입력해주세요.\n예: `trend btc 02/24 09:00 90000 02/25 09:00 95000 up`")

 
                    elif raw_cmd == 'now':
                        trigger_now_report = True
                    
                    elif raw_cmd == 'status':
                        interval_min = config.INTERVAL_SECONDS // 60
                        interval_sec = config.INTERVAL_SECONDS % 60
                        interval_str = f"{interval_min}분 {interval_sec}초" if interval_sec else f"{interval_min}분"
                        report_status = f"✅ ON ({interval_str} 주기)" if config.is_report_enabled else "❌ OFF"
                        alert_status = f"🔔 ON ({config.target_alignment})" if config.target_alignment else "🔕 OFF"
                        # 다음 알람 체크 시각 표시
                        if config.next_alert_time and (config.target_alignment or config.active_trendlines):
                            kst_time = config.next_alert_time + timedelta(hours=9)
                            next_check_str = kst_time.strftime('%H:%M:%S')
                        else:
                            next_check_str = "설정 안됨"
                            
                        # 추세선 알람 상태 문자열 생성
                        if config.active_trendlines:
                            trend_lines = ["📈 *활성 추세선:*"]
                            for sym, data in config.active_trendlines.items():
                                trend_lines.append(f"  • {sym}: {data['direction']}")
                            trend_status = "\n".join(trend_lines) + "\n"
                        else:
                            trend_status = "📉 *활성 추세선:* 없음\n"

                        msg = "⚙️ *모니터링 설정 현황*\n\n" \
                              f"• 타임프레임: `{config.TIMEFRAME}`\n" \
                              f"• 정기 리포트: `{report_status}`\n" \
                              f"• 지정 타겟 알람: `{alert_status}`\n" \
                              f"{trend_status}" \
                              f"• 다음 알람 체크: `{next_check_str} (KST)`"
                        send_telegram_message(msg)
 
                    elif raw_cmd in ['help', '/start']:
                        timeframes_str = ", ".join(config.SUPPORTED_TIMEFRAME)
                        align_list = "\n".join([f"  {k}: {v}" for k, v in config.ALIGNMENT_MAP.items()])
                        msg = f"🤖 *SMA 모니터 명령어 가이드*\n\n" \
                              f"📊 *리포트 설정*\n" \
                              f"• `report on/off`: 리포트 켜기/끄기\n" \
                              f"• `interval [초]`: 리포트 간격 설정 (예: `interval 60`)\n\n" \
                              f"🎯 *타겟 알림 (이평선)*\n" \
                              f"• `alert [번호]`: 특정 배열 시 알람 설정\n{align_list}\n" \
                              f"• `alert off`: 알람 해제\n\n" \
                              f"📈 *추세선 돌파 알림*\n" \
                              f"• `trend [코인] [월/일] [시:분] [가격] [월/일] [시:분] [가격] [up/down]`\n" \
                              f"  (예: `trend btc 02/24 09:00 90000 02/25 09:00 95000 up`)\n" \
                              f"• `trend off [코인]`: 추세선 알람 끄기 (예: `trend off btc`)\n\n" \
                              f"⚙️ *기타 명령어*\n" \
                              f"• `status`: 현재 설정 + 다음 체크 시각 확인\n" \
                              f"• `now`: 즉시 상황 보고\n\n" \
                              f"🕒 *타임프레임 변경*\n" \
                              f"• `{timeframes_str}` 중 하나 입력\n" \
                              f"  (예: `15m` 또는 `1h` 입력 시 즉시 변경)\n\n" \
                              f"💡 *알람 체크 방식*\n" \
                              f"• 설정된 봉이 마감될 때 자동 체크됩니다\n" \
                              f"• 예) 15m봉 → 매 :00, :15, :30, :45에 체크\n" \
                              f"• 예) 4h봉 → 09:00, 13:00, 17:00, 21:00, 01:00, 05:00에 체크"
                        send_telegram_message(msg)
                    
                    else:
                        send_telegram_message("❓ 인식할 수 없는 명령어입니다. 'help'를 입력해 사용 가능한 명령어를 확인하세요.")
                else:
                    print("DEBUG: Received non-text message", flush=True)
                    
    except Exception as e:
        print(f"Error getting updates: {e}", flush=True)
        
    return trigger_now_report
