import asyncio
import time
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from config import config
from src.detector import PumpDetector
from src.telegram_bot import TelegramNotifier
from src.utils import setup_logging

logger = setup_logging()

async def main_loop():
    detector = PumpDetector()
    notifier = TelegramNotifier()
    
    logger.info("="*50)
    logger.info("🚀 BYBIT PUMP DETECTOR v2.0 - FULL SCAN")
    logger.info(f"📊 Максимум монет: {config.MAX_SYMBOLS}")
    logger.info(f"🏆 Топ сигналов: {config.TOP_SIGNALS}")
    logger.info(f"⏱️  Интервал: {config.CHECK_INTERVAL} секунд")
    logger.info(f"🎯 Порог срабатывания: {config.SCORE_THRESHOLD}")
    logger.info(f"💰 Минимальный объём: ${config.MIN_VOLUME_USD:,.0f}")
    logger.info("="*50)
    
    while True:
        try:
            start_time = time.time()
            
            logger.info("🔍 Начинаем сканирование...")
            signals = detector.scan_all_symbols()
            
            # =========================================================
            # ОТПРАВЛЯЕМ ТОЛЬКО ЕСЛИ ЕСТЬ СИГНАЛЫ (С ЗВУКОМ!)
            # =========================================================
            if signals:
                await notifier.send_top_signals(signals)
                logger.info(f"✅ Отправлено {len(signals)} сигналов с звуком!")
                for s in signals:
                    logger.info(f"   {s['symbol']}: {s['score']}/100")
            else:
                # Просто логируем, НЕ отправляем в Telegram
                logger.info("ℹ️ Сигналов не найдено (тишина)")
            
            elapsed = time.time() - start_time
            wait_time = max(60, config.CHECK_INTERVAL - elapsed)
            logger.info(f"⏳ Ждём {wait_time:.0f} секунд до следующего сканирования...")
            logger.info("-"*50)
            await asyncio.sleep(wait_time)
            
        except KeyboardInterrupt:
            logger.info("👋 Бот остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"Критическая ошибка: {e}")
            await asyncio.sleep(60)

if __name__ == "__main__":
    try:
        config.validate()
        logger.info("✅ Настройки проверены успешно")
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен")
    except Exception as e:
        logger.error(f"Ошибка запуска: {e}")
        sys.exit(1)
