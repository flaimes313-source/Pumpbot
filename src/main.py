import asyncio
import time
import sys
from pathlib import Path
import signal

sys.path.append(str(Path(__file__).parent.parent))

from config import config
from src.detector import PumpDetector
from src.telegram_bot import TelegramNotifier
from src.utils import setup_logging

logger = setup_logging()

# Глобальные переменные для graceful shutdown
notifier = None
running = True

def signal_handler(sig, frame):
    """Обработчик сигналов для корректного завершения"""
    global running
    logger.info("👋 Получен сигнал остановки...")
    running = False

async def main_loop():
    global notifier, running
    
    detector = PumpDetector()
    notifier = TelegramNotifier()
    
    # Запускаем Telegram бота для обработки команд
    await notifier.start_bot()
    
    logger.info("="*50)
    logger.info("🚀 BYBIT PUMP DETECTOR v2.0 - FULL SCAN")
    logger.info(f"📊 Максимум монет: {config.MAX_SYMBOLS}")
    logger.info(f"🏆 Топ сигналов: {config.TOP_SIGNALS}")
    logger.info(f"⏱️  Интервал: {config.CHECK_INTERVAL} секунд")
    logger.info(f"🎯 Порог срабатывания: {config.SCORE_THRESHOLD}")
    logger.info(f"💰 Минимальный объём: ${config.MIN_VOLUME_USD:,.0f}")
    logger.info("="*50)
    logger.info("🤖 Бот запущен! Команды в Telegram: /start, /status, /help")
    logger.info("="*50)
    
    while running:
        try:
            start_time = time.time()
            
            logger.info("🔍 Начинаем сканирование...")
            signals = detector.scan_all_symbols()
            
            if signals:
                await notifier.send_top_signals(signals)
                logger.info(f"✅ Отправлено {len(signals)} сигналов с звуком!")
                for s in signals:
                    logger.info(f"   {s['symbol']}: {s['score']}/100")
            else:
                await notifier.send_scan_status(0)
                logger.info("ℹ️ Сигналов не найдено (тихое уведомление)")
            
            elapsed = time.time() - start_time
            wait_time = max(60, config.CHECK_INTERVAL - elapsed)
            logger.info(f"⏳ Ждём {wait_time:.0f} секунд до следующего сканирования...")
            logger.info("-"*50)
            
            # Ждём с возможностью прерывания
            for _ in range(int(wait_time)):
                if not running:
                    break
                await asyncio.sleep(1)
            
        except asyncio.CancelledError:
            logger.info("👋 Цикл сканирования остановлен")
            break
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            await asyncio.sleep(60)

async def shutdown():
    """Корректное завершение работы"""
    global notifier
    logger.info("🛑 Останавливаем бота...")
    if notifier:
        await notifier.stop_bot()
    logger.info("👋 Бот остановлен")

if __name__ == "__main__":
    try:
        # Настраиваем обработку сигналов
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Проверяем настройки
        config.validate()
        logger.info("✅ Настройки проверены успешно")
        
        # Запускаем бота
        asyncio.run(main_loop())
        
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
        sys.exit(1)
    finally:
        # Корректное завершение
        asyncio.run(shutdown())
