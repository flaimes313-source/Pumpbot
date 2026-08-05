from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import config
import logging
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Отправка уведомлений в Telegram"""
    
    def __init__(self):
        self.bot = Bot(token=config.TELEGRAM_TOKEN)
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.application = None
        self.is_scanning = False
        self.scan_task = None
        self.detector = None
        logger.info("Telegram бот инициализирован")
    
    def set_detector(self, detector):
        """Устанавливает детектор для сканирования"""
        self.detector = detector
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработчик команды /start
        Запускает сканирование и отправляет приветствие
        """
        user = update.effective_user
        user_name = user.first_name if user.first_name else "Пользователь"
        
        # Если сканирование уже запущено
        if self.is_scanning:
            await update.message.reply_text(
                f"👋 <b>Привет, {user_name}!</b>\n\n"
                f"✅ <b>Сканирование УЖЕ запущено!</b>\n"
                f"🔄 Бот работает в фоновом режиме.\n\n"
                f"📊 Статус: Активен\n"
                f"⏱️ Интервал: {config.CHECK_INTERVAL} сек\n"
                f"🎯 Порог: {config.SCORE_THRESHOLD}/100\n\n"
                f"📱 Команды:\n"
                f"/start - Запустить/проверить статус\n"
                f"/status - Статус сканирования\n"
                f"/stop - Остановить сканирование\n"
                f"/help - Помощь",
                parse_mode='HTML'
            )
            return
        
        # Запускаем сканирование
        self.is_scanning = True
        await update.message.reply_text(
            f"👋 <b>Привет, {user_name}!</b>\n\n"
            f"🚀 <b>ЗАПУСКАЮ СКАНИРОВАНИЕ...</b>\n\n"
            f"📊 <b>Настройки:</b>\n"
            f"• Максимум монет: {config.MAX_SYMBOLS}\n"
            f"• Топ сигналов: {config.TOP_SIGNALS}\n"
            f"• Порог срабатывания: {config.SCORE_THRESHOLD}/100\n"
            f"• Интервал сканирования: {config.CHECK_INTERVAL} сек\n"
            f"• Минимальный объём: ${config.MIN_VOLUME_USD:,.0f}\n\n"
            f"🔍 <b>Что я проверяю:</b>\n"
            f"• 📈 Всплеск объёма (+30 баллов)\n"
            f"• 💰 Рост Open Interest (+20 баллов)\n"
            f"• ⚡ Изменение Funding (+15 баллов)\n"
            f"• 📊 Рост цены (+15 баллов)\n\n"
            f"📱 <b>Команды:</b>\n"
            f"/start - Запустить/проверить статус\n"
            f"/status - Статус сканирования\n"
            f"/stop - Остановить сканирование\n"
            f"/help - Помощь\n\n"
            f"✅ <b>Сканирование запущено!</b>",
            parse_mode='HTML'
        )
        
        # Запускаем фоновое сканирование
        if self.detector:
            self.scan_task = asyncio.create_task(self._run_scanning())
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработчик команды /stop
        Останавливает сканирование
        """
        if not self.is_scanning:
            await update.message.reply_text(
                "⚠️ Сканирование уже остановлено.\n"
                "Для запуска используйте /start",
                parse_mode='HTML'
            )
            return
        
        self.is_scanning = False
        if self.scan_task:
            self.scan_task.cancel()
            self.scan_task = None
        
        await update.message.reply_text(
            "🛑 <b>Сканирование ОСТАНОВЛЕНО!</b>\n\n"
            "Для возобновления используйте /start",
            parse_mode='HTML'
        )
        logger.info("⏹️ Сканирование остановлено по команде /stop")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /status"""
        status = "✅ АКТИВЕН" if self.is_scanning else "⏸️ ОСТАНОВЛЕН"
        
        message = f"""
📊 <b>СТАТУС БОТА</b>
🕐 {datetime.now().strftime('%H:%M:%S')}

📈 <b>Статус сканирования:</b> {status}

📊 <b>Настройки:</b>
• Интервал: {config.CHECK_INTERVAL} сек
• Порог: {config.SCORE_THRESHOLD}/100
• Максимум монет: {config.MAX_SYMBOLS}
• Топ сигналов: {config.TOP_SIGNALS}

📱 <b>Команды:</b>
/start - Запустить сканирование
/stop - Остановить сканирование
/status - Этот статус
/help - Помощь
"""
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        message = """
❓ <b>ПОМОЩЬ</b>

📌 <b>Что делает бот?</b>
Сканирует Bybit и ищет потенциальные пампы.

📌 <b>Как запустить?</b>
Команда <b>/start</b> - запускает сканирование

📌 <b>Как остановить?</b>
Команда <b>/stop</b> - останавливает сканирование

📌 <b>Как работают сигналы?</b>
Каждые 5 минут бот проверяет монеты.
Если находит памп - присылает <b>СО ЗВУКОМ</b> 🔔
Если сигналов нет - присылает <b>БЕЗ ЗВУКА</b> 📊

📌 <b>Что значат баллы?</b>
• 80-100: 🔴 ВЫСОКАЯ вероятность
• 70-79: 🟡 СРЕДНЯЯ вероятность
• 60-69: 🟢 НИЗКАЯ вероятность

📌 <b>Как я считаю?</b>
• Всплеск объёма → до 30 баллов
• Рост OI → до 20 баллов
• Funding → до 15 баллов
• Рост цены → до 15 баллов

──────────────
⚙️ <b>Команды:</b>
/start - Запустить сканирование
/stop - Остановить сканирование
/status - Статус бота
/help - Эта справка

⚠️ <i>Все решения по торговле - на ваш страх и риск.</i>
"""
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def _run_scanning(self):
        """Фоновое сканирование"""
        logger.info("🔄 Запущено фоновое сканирование")
        
        while self.is_scanning and self.detector:
            try:
                logger.info("🔍 Начинаем сканирование...")
                signals = self.detector.scan_all_symbols()
                
                if signals:
                    await self.send_top_signals(signals)
                    logger.info(f"✅ Отправлено {len(signals)} сигналов с звуком!")
                    for s in signals:
                        logger.info(f"   {s['symbol']}: {s['score']}/100")
                else:
                    await self.send_scan_status(0)
                    logger.info("ℹ️ Сигналов не найдено (тихое уведомление)")
                
                # Ждём до следующего сканирования
                for _ in range(config.CHECK_INTERVAL):
                    if not self.is_scanning:
                        break
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                logger.info("👋 Фоновое сканирование отменено")
                break
            except Exception as e:
                logger.error(f"Ошибка в фоновом сканировании: {e}")
                await asyncio.sleep(60)
        
        logger.info("⏹️ Фоновое сканирование завершено")
    
    async def send_message(self, text, silent=False):
        """Отправка сообщения"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True,
                disable_notification=silent
            )
            logger.info(f"Сообщение отправлено в Telegram (silent={silent})")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
            return False
    
    async def send_scan_status(self, signals_count):
        """Отправка статуса сканирования (БЕЗ ЗВУКА)"""
        message = f"""
📊 <b>Сканирование завершено</b>
🕐 {datetime.now().strftime('%H:%M:%S')}

📈 Найдено сигналов: <b>{signals_count}</b>
{'🔍 Продолжаем мониторинг...' if signals_count == 0 else '🚀 Есть потенциальные пампы!'}
"""
        return await self.send_message(message, silent=True)
    
    async def send_top_signals(self, signals):
        """Отправка топ сигналов (СО ЗВУКОМ)"""
        if not signals:
            return await self.send_scan_status(0)
        
        await self.send_scan_status(len(signals))
        
        message = f"""
🔔🔊 <b>ВНИМАНИЕ! ОБНАРУЖЕНЫ ПАМП-СИГНАЛЫ!</b>

🚀 <b>ТОП-{min(len(signals), config.TOP_SIGNALS)} ПАМП СИГНАЛОВ</b>
📅 {datetime.now().strftime('%H:%M:%S')}
📊 Всего найдено: {len(signals)}

"""
        
        for i, signal in enumerate(signals[:config.TOP_SIGNALS], 1):
            if signal['score'] >= 80:
                prob = "🔴 ВЫСОКАЯ"
                star = "⭐"
            elif signal['score'] >= 70:
                prob = "🟡 СРЕДНЯЯ"
                star = "🌟"
            else:
                prob = "🟢 НИЗКАЯ"
                star = "💫"
            
            message += f"""
<b>{star} #{i} {signal['symbol']}</b>
┌─────────────────────
│ 📊 Рейтинг: <b>{signal['score']}/100</b> | {prob}
│ 📈 Цена: +{signal['price_change']:.2f}%
│ 📊 Объём: {signal['volume_ratio']:.1f}x от среднего
│ 💰 OI: +{signal['oi_change']:.1f}%
│ ⚡ Funding: {signal['funding']*100:.4f}%
│ 📉 До сопротивления: {signal['resistance_gap']:.1f}%
└─────────────────────
"""
        
        message += """
⚠️ <i>Торговля криптовалютами связана с высоким риском.
Все решения принимайте на свой страх и риск.</i>
"""
        
        return await self.send_message(message, silent=False)
    
    async def run_bot(self):
        """Запуск Telegram бота"""
        try:
            logger.info("🔄 Запускаем Telegram бота...")
            
            self.application = Application.builder().token(config.TELEGRAM_TOKEN).build()
            
            # Регистрируем команды
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("stop", self.stop_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("✅ Telegram бот запущен! Команды: /start, /stop, /status, /help")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telegram бота: {e}")
            return False
    
    async def stop_bot(self):
        """Остановка Telegram бота"""
        self.is_scanning = False
        if self.scan_task:
            self.scan_task.cancel()
        
        try:
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Telegram бот остановлен")
        except Exception as e:
            logger.error(f"Ошибка остановки Telegram бота: {e}")
