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
        
        # ============================================================
        # ПРЕДВАРИТЕЛЬНАЯ ЗАГРУЗКА СИМВОЛОВ (ОДИН РАЗ ПРИ СТАРТЕ)
        # ============================================================
        logger.info("🔄 Предварительная загрузка символов...")
        symbols = detector.client.load_all_symbols()
        if symbols:
            symbols_to_watch = symbols[:config.MAX_SYMBOLS]
            logger.info(f"📊 Загружено {len(symbols_to_watch)} символов")
        else:
            logger.warning("⚠️ Не удалось загрузить символы")
        # ============================================================
        
        # Запускаем WebSocket
        try:
            logger.info("🔄 Запускаем TradeStream...")
            if symbols:
                asyncio.create_task(trade_stream.connect(symbols_to_watch))
                logger.info(f"✅ TradeStream запущен для {len(symbols_to_watch)} символов")
            else:
                logger.warning("⚠️ TradeStream не запущен — нет символов")
        except Exception as e:
            logger.error(f"❌ Ошибка запуска TradeStream: {e}")
            logger.info("ℹ️ TradeStream будет работать в режиме эмуляции")
            trade_stream.use_websocket = False
            asyncio.create_task(trade_stream._emulate_trades())
        
        logger.info("="*50)
        logger.info("🚀 BYBIT PUMP DETECTOR v2.0")
        logger.info(f"📊 Максимум монет: {config.MAX_SYMBOLS}")
        logger.info(f"🏆 Топ сигналов: {config.TOP_SIGNALS}")
        logger.info(f"⏱️  Интервал: {config.CHECK_INTERVAL} секунд")
        logger.info(f"🎯 Порог Стадии 1: 50/130")
        logger.info(f"🎯 Порог Стадии 2: 70/130")
        logger.info("="*50)
        logger.info("📊 НОВЫЕ УЛУЧШЕНИЯ:")
        logger.info("   ✅ Кеширование символов (загрузка 1 раз)")
        logger.info("   ✅ Асинхронное сканирование")
        logger.info("   ✅ Команды работают ВО ВРЕМЯ сканирования")
        logger.info("="*50)
        logger.info("🤖 Бот запущен!")
        logger.info("📱 Команды в Telegram: /start, /stop, /pause, /resume, /result, /stats, /status, /help")
        logger.info("="*50)
        
        # Запускаем Telegram бота
        await notifier.run_bot()
        
        # Основной цикл
        logger.info("⏳ Ожидание команд из Telegram...")
        while True:
            try:
                if not notifier.is_scanning:
                    await asyncio.sleep(1)
                    continue
                
                if not notifier.is_paused and detector:
                    logger.info("🔍 Начинаем асинхронное сканирование...")
                    
                    # Символы уже загружены, сканируем без задержки
                    if hasattr(detector, 'scan_all_symbols_async'):
                        signals = await detector.scan_all_symbols_async()
                    else:
                        signals = await asyncio.to_thread(detector.scan_all_symbols)
                    
                    if signals:
                        await notifier.send_top_signals(signals)
                        logger.info(f"✅ Отправлено {len(signals)} сигналов")
                    else:
                        logger.info("ℹ️ Сигналов не найдено (тишина)")
                
                for _ in range(config.CHECK_INTERVAL):
                    if not notifier.is_scanning or notifier.is_paused:
                        break
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                logger.info("👋 Цикл сканирования отменён")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в основном цикле: {e}")
                await asyncio.sleep(60)
        
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
        raise
    finally:
        trade_stream.stop()
        logger.info("✅ TradeStream остановлен")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Ошибка запуска: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)