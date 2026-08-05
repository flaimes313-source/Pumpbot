import asyncio
import sys
from pathlib import Path
import signal

sys.path.append(str(Path(__file__).parent.parent))

from config import config
from src.detector import PumpDetector
from src.telegram_bot import TelegramNotifier
from src.utils import setup_logging

logger = setup_logging()

# Глобальные переменные
notifier = None
running = True

def signal_handler(sig, frame):
    """Обработчик сигналов"""
    global running
    logger.info("👋 Получен сигнал остановки...")
    running = False

async def main():
    global notifier, running
    
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
    logger.info(f"🎯 Порог срабатывания: {config.SCORE_THRESHOLD}")
    logger.info("="*50)
    logger.info("🤖 Бот запущен! Команды в Telegram:")
    logger.info("   /start  - Запустить сканирование")
    logger.info("   /stop   - Остановить сканирование")
    logger.info("   /status - Статус бота")
    logger.info("   /help   - Помощь")
    logger.info("="*50)
    
    # Запускаем Telegram бота
    await notifier.run_bot()
    
    # Держим бота активным
    while running:
        await asyncio.sleep(1)

async def shutdown():
    """Корректное завершение"""
    global notifier
    logger.info("🛑 Останавливаем бота...")
    if notifier:
        await notifier.stop_bot()
    logger.info("👋 Бот остановлен")

if __name__ == "__main__":
    try:
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        config.validate()
        logger.info("✅ Настройки проверены успешно")
        
        asyncio.run(main())
        
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
        sys.exit(1)
    finally:
        try:
            asyncio.run(shutdown())
        except:
            pass
