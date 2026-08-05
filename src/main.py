import asyncio
import sys
from pathlib import Path

# Добавляем корневую папку в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from src.detector import PumpDetector
from src.telegram_bot import TelegramNotifier
from src.utils import setup_logging

logger = setup_logging()

async def main():
    """Запуск бота"""
    try:
        # Проверяем настройки
        config.validate()
        logger.info("✅ Настройки проверены успешно")
        
        # Создаём детектор и нотификатор
        detector = PumpDetector()
        notifier = TelegramNotifier()
        
        # Передаём детектор в нотификатор
        notifier.set_detector(detector)
        
        logger.info("="*50)
        logger.info("🚀 BYBIT PUMP DETECTOR v2.0")
        logger.info(f"📊 Максимум монет: {config.MAX_SYMBOLS}")
        logger.info(f"🏆 Топ сигналов: {config.TOP_SIGNALS}")
        logger.info(f"⏱️  Интервал: {config.CHECK_INTERVAL} секунд")
        logger.info(f"🎯 Порог срабатывания: {config.SCORE_THRESHOLD}/130")
        logger.info("="*50)
        logger.info("🤖 Бот запущен!")
        logger.info("📱 Команды в Telegram: /start, /stop, /status, /help")
        logger.info("="*50)
        
        # Запускаем Telegram бота
        await notifier.run_bot()
        
        # Держим бота активным
        logger.info("⏳ Ожидание команд из Telegram...")
        while True:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
