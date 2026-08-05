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
        """Команда /start - запускает сканирование"""
        user = update.effective_user
        user_name = user.first_name if user.first_name else "Пользователь"
        
        # Если сканирование уже запущено
        if self.is_scanning:
            await update.message.reply_text(
                f"👋 Привет, {user_name}!\n\n"
                f"✅ Сканирование УЖЕ запущено!\n"
                f"🔄 Бот работает в фоновом режиме.\n\n"
                f"📊 <b>Новые индикаторы:</b>\n"
                f"• 📈 OI за 5/15/30 минут\n"
                f"• 📉 CVD (дельта покупок/продаж)\n"
                f"• 📊 Bid/Ask дисбаланс\n"
                f"• ⚡ Ускорение цены\n"
                f"• 🔥 Ликвидации\n"
                f"• 🤝 Синергия Volume+OI\n\n"
                f"📱 Команды:\n"
                f"/start - Запустить/проверить статус\n"
                f"/stop - Остановить сканирование\n"
                f"/status - Статус\n"
                f"/help - Помощь",
                parse_mode='HTML'
            )
            return
        
        # Запускаем сканирование
        self.is_scanning = True
        await update.message.reply_text(
            f"👋 Привет, {user_name}!\n\n"
            f"🚀 ЗАПУСКАЮ СКАНИРОВАНИЕ...\n\n"
            f"📊 <b>Настройки:</b>\n"
            f"• Интервал: {config.CHECK_INTERVAL} сек\n"
            f"• Порог: {config.SCORE_THRESHOLD}/130\n"
            f"• Максимум монет: {config.MAX_SYMBOLS}\n\n"
            f"📊 <b>Новые индикаторы:</b>\n"
            f"• 📈 OI за 5/15/30 минут (до 25 баллов)\n"
            f"• 📉 CVD (дельта) (до 15 баллов)\n"
            f"• 📊 Bid/Ask дисбаланс (до 10 баллов)\n"
            f"• ⚡ Ускорение цены (до 10 баллов)\n"
            f"• 🔥 Ликвидации (до 15 баллов)\n"
            f"• 🤝 Синергия Volume+OI (до 10 баллов)\n\n"
            f"✅ Сканирование запущено!",
            parse_mode='HTML'
        )
        
        # Запускаем фоновое сканирование
        if self.detector:
            self.scan_task = asyncio.create_task(self._run_scanning())
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stop - останавливает сканирование"""
        if not self.is_scanning:
            await update.message.reply_text("⚠️ Сканирование уже остановлено.")
            return
        
        self.is_scanning = False
        if self.scan_task:
            self.scan_task.cancel()
            self.scan_task = None
        
        await update.message.reply_text("🛑 Сканирование ОСТАНОВЛЕНО!\nДля запуска используйте /start")
        logger.info("⏹️ Сканирование остановлено по команде /stop")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status - показывает статус"""
        status = "✅ АКТИВЕН" if self.is_scanning else "⏸️ ОСТАНОВЛЕН"
        await update.message.reply_text(
            f"📊 <b>СТАТУС БОТА</b>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"📈 Статус сканирования: {status}\n"
            f"⏱️ Интервал: {config.CHECK_INTERVAL} сек\n"
            f"🎯 Порог: {config.SCORE_THRESHOLD}/130\n"
            f"📊 Максимум монет: {config.MAX_SYMBOLS}\n\n"
            f"📊 <b>Новые индикаторы:</b>\n"
            f"• OI 5/15/30 мин\n"
            f"• CVD (дельта)\n"
            f"• Bid/Ask дисбаланс\n"
            f"• Ускорение цены\n"
            f"• Ликвидации\n"
            f"• Синергия Volume+OI\n\n"
            f"📱 Команды:\n"
            f"/start - Запустить\n"
            f"/stop - Остановить\n"
            f"/status - Статус\n"
            f"/help - Помощь",
            parse_mode='HTML'
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - показывает помощь"""
        await update.message.reply_text(
            "❓ <b>ПОМОЩЬ</b>\n\n"
            "📌 <b>Что делает бот?</b>\n"
            "Сканирует Bybit и ищет пампы.\n\n"
            "📌 <b>Новые индикаторы:</b>\n"
            "• 📈 OI за 5/15/30 минут\n"
            "• 📉 CVD (дельта покупок/продаж)\n"
            "• 📊 Bid/Ask дисбаланс в стакане\n"
            "• ⚡ Ускорение цены\n"
            "• 🔥 Ликвидации шортов/лонгов\n"
            "• 🤝 Синергия объёма и OI\n\n"
            "📌 <b>Как запустить?</b>\n"
            "Команда /start\n\n"
            "📌 <b>Как остановить?</b>\n"
            "Команда /stop\n\n"
            "📌 <b>Как работают сигналы?</b>\n"
            "Каждые 5 минут бот проверяет монеты.\n"
            "Если находит памп - присылает <b>СО ЗВУКОМ</b> 🔔\n"
            "Если сигналов нет - присылает <b>БЕЗ ЗВУКА</b> 📊\n\n"
            "📱 <b>Команды:</b>\n"
            "/start - Запустить\n"
            "/stop - Остановить\n"
            "/status - Статус\n"
            "/help - Помощь",
            parse_mode='HTML'
        )
    
    async def _run_scanning(self):
        """Фоновое сканирование"""
        logger.info("🔄 Запущено фоновое сканирование")
        
        while self.is_scanning and self.detector:
            try:
                logger.info("🔍 Начинаем сканирование...")
                signals = self.detector.scan_all_symbols()
                
                if signals:
                    await self.send_top_signals(signals)
                else:
                    await self.send_scan_status(0)
                
                # Ждём до следующего сканирования
                for _ in range(config.CHECK_INTERVAL):
                    if not self.is_scanning:
                        break
                    await asyncio.sleep(1)
                    
            except asyncio.CancelledError:
                logger.info("👋 Фоновое сканирование отменено")
                break
            except Exception as e:
                logger.error(f"❌ Ошибка в фоновом сканировании: {e}")
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
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки: {e}")
            return False
    
    async def send_scan_status(self, signals_count):
        """Отправка статуса (БЕЗ ЗВУКА)"""
        message = f"""
📊 <b>Сканирование завершено</b>
🕐 {datetime.now().strftime('%H:%M:%S')}

📈 Найдено сигналов: <b>{signals_count}</b>
{'🔍 Продолжаем мониторинг...' if signals_count == 0 else '🚀 Есть потенциальные пампы!'}
"""
        await self.send_message(message, silent=True)
    
    async def send_top_signals(self, signals):
        """Отправка сигналов (СО ЗВУКОМ) с новыми индикаторами"""
        await self.send_scan_status(len(signals))
        
        message = f"""
🔔🔊 <b>ВНИМАНИЕ! ОБНАРУЖЕНЫ ПАМП-СИГНАЛЫ!</b>

🚀 <b>ТОП-{min(len(signals), config.TOP_SIGNALS)} ПАМП СИГНАЛОВ</b>
📅 {datetime.now().strftime('%H:%M:%S')}
📊 Всего найдено: {len(signals)}

"""
        
        for i, signal in enumerate(signals[:config.TOP_SIGNALS], 1):
            # Определяем вероятность
            if signal['score'] >= 100:
                prob = "🔴 ВЫСОКАЯ"
                star = "⭐"
            elif signal['score'] >= 80:
                prob = "🟡 СРЕДНЯЯ"
                star = "🌟"
            else:
                prob = "🟢 НИЗКАЯ"
                star = "💫"
            
            # Синергия
            synergy_text = "✅" if signal.get('synergy', False) else "❌"
            
            # Ликвидации
            liq_text = ""
            if signal.get('liq_short', 0) > signal.get('liq_long', 0) * 1.5:
                liq_text = "🟢 Шортов больше"
            elif signal.get('liq_long', 0) > signal.get('liq_short', 0) * 1.5:
                liq_text = "🔴 Лонгов больше"
            
            message += f"""
<b>{star} #{i} {signal['symbol']}</b>
┌─────────────────────────────────────
│ 📊 Рейтинг: <b>{signal['score']}/130</b> | {prob}
│ 📈 Цена: +{signal['price_change']:.2f}%
│ 📊 Объём: {signal['volume_ratio']:.1f}x
│ 💰 OI: +{signal['oi_change']:.1f}%
│ 📉 CVD: {signal.get('cvd', 0):.0f}
│ 📊 Bid/Ask: {signal.get('bid_imbalance', 0):.1f}%
│ ⚡ Ускорение: {signal.get('acceleration', 1):.1f}x
│ 🔥 Ликвидации: ${signal.get('liq_total', 0)/1e6:.2f}M {liq_text}
│ 📉 До сопротивления: {signal['resistance_gap']:.1f}%
│ 🤝 Синергия Volume+OI: {synergy_text}
└─────────────────────────────────────
"""
        
        message += """
⚠️ <i>Торговля криптовалютами связана с высоким риском.
Все решения принимайте на свой страх и риск.</i>
"""
        
        await self.send_message(message, silent=False)
    
    async def run_bot(self):
        """Запуск Telegram бота"""
        try:
            logger.info("🔄 Запускаем Telegram бота...")
            
            self.application = Application.builder().token(config.TELEGRAM_TOKEN).build()
            
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