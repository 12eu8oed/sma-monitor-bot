import os
from dotenv import load_dotenv
from datetime import datetime

# ==========================================
# 1. 환경 변수 로드
# ==========================================
load_dotenv()
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# ==========================================
# 2. 고정 설정 (Constants)
# ==========================================
SYMBOLS = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'SOL/USDT']
SMA_PERIODS = [7, 25, 99]
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

# ==========================================
# 3. 글로벌 상태 변수 (Global State)
# ==========================================
# 모듈을 임포트해서 config.TIMEFRAME 형태로 접근 및 수정
TIMEFRAME = '5m'
INTERVAL_SECONDS = 60  # 정기 리포트 간격 (60초 = 1분)
is_report_enabled = True      # 정기 리포트 활성화 여부
target_alignment = None       # 알림을 받을 타겟 배열 (예: '7>25>99')
alert_sent_state = {symbol: False for symbol in SYMBOLS} # 코인별 알림 중복 방지
next_alert_time = None        # 다음 알람 체크 시각 (UTC)
active_trendlines = {}        # 코인별 설정된 추세선 좌표 저장

last_update_id = 0
last_report_time = datetime.min
get_updates_call_count = 0
