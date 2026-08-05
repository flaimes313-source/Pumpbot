import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from src.detector import PumpDetector
from src.telegram_bot import TelegramNotifier
from src.utils import setup_logging
from src.trade_stream import trade_stream

logger = setup_logging()

async def main():
    """Запуск бота"""
    try:
        config.validate()
        logger.info("✅ Настройки проверены успешно")
        
        # Создаём детектор и нотификатор
        detector = PumpDetector()
        notifier = TelegramNotifier()
        
        # Передаём детектор в нотификатор
        notifier.set_detector(detector)
        
        # Загружаем символы для WebSocket
        symbols = detector.client.load_all_symbols()
        if symbols:
            symbols_to_watch = symbols[:config.MAX_SYMBOLS]
            # Запускаем WebSocket в фоне
            asyncio.create_task(trade_stream.connect(symbols_to_watch))
            logger.info(f"✅ WebSocket запущен для {len(symbols_to_watch)} символов")
        
        logger.info("="*50)
        logger.info("🚀 BYBIT PUMP DETECTOR v2.0")
        logger.info(f"📊 Максимум монет: {config.MAX_SYMBOLS}")
        logger.info(f"🏆 Топ сигналов: {config.TOP_SIGNALS}")
        logger.info(f"⏱️  Интервал: {config.CHECK_INTERVAL} секунд")
        logger.info(f"🎯 Порог Стадии 1: 50/130")
        logger.info(f"🎯 Порог Стадии 2: 70/130")
        logger.info("="*50)
        logger.info("📊 <b>НОВЫЕ УЛУЧШЕНИЯ:</b>")
        logger.info("   ✅ Реальный Trade Count (WebSocket)")
        logger.info("   ✅ Асинхронное сканирование (asyncio.gather)")
        logger.info("   ✅ Динамические пороги (на основе ATR)")
        logger.info("   ✅ Команда /pause (поставить на паузу)")
        logger.info("="*50)
        logger.info("🤖 Бот запущен!")
        logger.info("📱 Команды в Telegram:")
        logger.info("   /start   - Запустить сканирование")
        logger.info("   /stop    - Остановить сканирование")
        logger.info("   /pause   - Поставить на паузу")
        logger.info("   /resume  - Возобновить работу")
        logger.info("   /status  - Статус бота")
        logger.info("   /help    - Помощь")
        logger.info("="*50)
        
        # Запускаем Telegram бота
        await notifier.run_bot()
        
        # Основной цикл сканирования
        logger.info("⏳ Ожидание команд из Telegram...")
        while True:
            try:
                # Ждём команды
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Ошибка в основном цикле: {e}")
                await asyncio.sleep(5)
            
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка: {e}")
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
        sys.exit(1)