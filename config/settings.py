import os
from dotenv import load_dotenv
import sys
from pathlib import Path

# Добавляем корневую папку в путь
sys.path.append(str(Path(__file__).parent.parent))

# Указываем путь к .env файлу
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

class Config:
    # Telegram (ОБЯЗАТЕЛЬНО!)
    TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # Настройки сканирования
    MAX_SYMBOLS = int(os.getenv('MAX_SYMBOLS', 50))
    TOP_SIGNALS = int(os.getenv('TOP_SIGNALS', 5))
    MIN_VOLUME_USD = float(os.getenv('MIN_VOLUME_USD', 500_000))
    
    # Временные настройки
    TIMEFRAME = os.getenv('TIMEFRAME', '5')
    CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 300))
    
    # Пороги для баллов
    SCORE_THRESHOLD = int(os.getenv('SCORE_THRESHOLD', 60))
    VOLUME_RATIO_20 = float(os.getenv('VOLUME_RATIO_20', 2.0))
    VOLUME_RATIO_30 = float(os.getenv('VOLUME_RATIO_30', 3.0))
    OI_CHANGE_15M = float(os.getenv('OI_CHANGE_15M', 7.0))
    PRICE_CHANGE_5M = float(os.getenv('PRICE_CHANGE_5M', 1.5))
    FUNDING_SPIKE = float(os.getenv('FUNDING_SPIKE', 0.03))
    
    # Фильтры
    ATR_MAX_PERCENT_24H = float(os.getenv('ATR_MAX_PERCENT_24H', 2.5))
    ATR_MAX_PERCENT_4H = float(os.getenv('ATR_MAX_PERCENT_4H', 1.8))
    RESISTANCE_GAP_MIN = float(os.getenv('RESISTANCE_GAP_MIN', 3.0))
    
    @classmethod
    def validate(cls):
        errors = []
        if not cls.TELEGRAM_TOKEN:
            errors.append("TELEGRAM_TOKEN не задан! Получите у @BotFather")
        if not cls.TELEGRAM_CHAT_ID:
            errors.append("TELEGRAM_CHAT_ID не задан! Получите у @userinfobot")
        if errors:
            raise ValueError("\n".join(errors))
        return True

config = Config()