import sys
import io
import os
from datetime import datetime, timedelta, timezone
import config

# ==========================================
# 운영체제 맞춤 설정 (교차 플랫폼 지원)
# ==========================================
IS_WINDOWS = sys.platform == 'win32'

def setup_os_environment():
    """운영체제 환경에 따른 초기 설정 (예: 윈도우 인코딩)"""
    if IS_WINDOWS:
        # 윈도우 인코딩 문제 해결 (이모지 출력 지원)
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def check_single_instance():
    """하나의 인스턴스만 실행되도록 보장 (파일 잠금 활용)"""
    try:
        f = open(config.LOCK_FILE, "w")
        if IS_WINDOWS:
            import msvcrt
            # Windows: msvcrt.locking
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            # Unix/macOS: fcntl.lockf
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return f
    except (IOError, OSError):
        print("\n❌ [오류] 이미 프로그램이 실행 중입니다. 중복 실행을 차단합니다.")
        return None

# ==========================================
# 수학 / 시간 유틸리티
# ==========================================
def get_next_candle_close(timeframe):
    """현재 시각 기준으로 다음 봉 마감 시각(UTC)을 계산"""
    now_utc = datetime.now(timezone.utc)
    minutes = config.TIMEFRAME_MINUTES.get(timeframe, 5)
    
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
