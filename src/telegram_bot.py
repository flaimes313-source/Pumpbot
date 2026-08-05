from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import config
import logging
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Отправка уведомлений в Telegram с двухстадийной системой"""
    
    def __init__(self):
        self.bot = Bot(token=config.TELEGRAM_TOKEN)
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.application = None
        self.is_scanning = False
        self.is_paused = False
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
            status_text = "⏸️ НА ПАУЗЕ" if self.is_paused else "✅ АКТИВЕН"
            await update.message.reply_text(
                f"👋 Привет, {user_name}!\n\n"
                f"✅ Сканирование УЖЕ запущено!\n"
                f"📊 Статус: {status_text}\n"
                f"🔄 Бот работает в фоновом режиме.\n\n"
                f"📊 <b>Двухстадийная система:</b>\n"
                f"🟡 Стадия 1 — Раннее предупреждение (50-69 баллов)\n"
                f"🟢 Стадия 2 — Памп/Дамп подтвержден (70+ баллов)\n\n"
                f"🎯 <b>Направление:</b>\n"
                f"🟢 LONG — памп вверх\n"
                f"🔴 SHORT — дамп вниз\n\n"
                f"📊 <b>Индикаторы:</b>\n"
                f"• 📈 OI за 5/15/30 минут\n"
                f"• 📉 CVD (дельта покупок/продаж)\n"
                f"• 📊 Bid/Ask дисбаланс (Top 25)\n"
                f"• ⚡ Ускорение цены (только вверх)\n"
                f"• 🔥 Ликвидации\n"
                f"• 🤝 Синергия Volume+OI\n"
                f"• 📊 Реальный Trade Count (WebSocket)\n\n"
                f"📱 Команды:\n"
                f"/start - Запустить/проверить статус\n"
                f"/stop - Остановить сканирование\n"
                f"/pause - Поставить на паузу\n"
                f"/resume - Возобновить работу\n"
                f"/status - Статус\n"
                f"/help - Помощь",
                parse_mode='HTML'
            )
            return
        
        # Запускаем сканирование
        self.is_scanning = True
        self.is_paused = False
        await update.message.reply_text(
            f"👋 Привет, {user_name}!\n\n"
            f"🚀 ЗАПУСКАЮ СКАНИРОВАНИЕ...\n\n"
            f"📊 <b>Настройки:</b>\n"
            f"• Интервал: {config.CHECK_INTERVAL} сек\n"
            f"• Порог Стадии 1: 50/130\n"
            f"• Порог Стадии 2: 70/130\n"
            f"• Максимум монет: {config.MAX_SYMBOLS}\n\n"
            f"📊 <b>Двухстадийная система:</b>\n"
            f"🟡 Стадия 1 — Раннее предупреждение\n"
            f"   Объём и OI растут, цена ещё не ушла\n"
            f"🟢 Стадия 2 — Памп/Дамп подтвержден\n"
            f"   Цена пробила, движение подтверждено\n\n"
            f"🎯 <b>Направление:</b>\n"
            f"🟢 LONG — памп вверх\n"
            f"🔴 SHORT — дамп вниз\n\n"
            f"📊 <b>Новые улучшения:</b>\n"
            f"✅ Реальный Trade Count (WebSocket)\n"
            f"✅ Динамические пороги (на основе ATR)\n"
            f"✅ Команда /pause для паузы\n\n"
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
        self.is_paused = False
        if self.scan_task:
            self.scan_task.cancel()
            self.scan_task = None
        
        # Снимаем паузу с детектора
        if self.detector:
            self.detector.resume()
        
        await update.message.reply_text(
            "🛑 <b>Сканирование ОСТАНОВЛЕНО!</b>\n\n"
            "Для запуска используйте /start",
            parse_mode='HTML'
        )
        logger.info("⏹️ Сканирование остановлено по команде /stop")
    
    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /pause - поставить сканирование на паузу"""
        if not self.is_scanning:
            await update.message.reply_text(
                "⚠️ Сканирование не запущено.\n"
                "Используйте /start для запуска.",
                parse_mode='HTML'
            )
            return
        
        if self.is_paused:
            await update.message.reply_text(
                "⏸️ Сканирование УЖЕ на паузе.\n"
                "Для возобновления используйте /resume",
                parse_mode='HTML'
            )
            return
        
        self.is_paused = True
        if self.detector:
            self.detector.pause()
        
        await update.message.reply_text(
            "⏸️ <b>Сканирование поставлено на ПАУЗУ!</b>\n\n"
            "🔄 Бот активен, но не сканирует рынок.\n"
            "▶️ Для возобновления используйте /resume",
            parse_mode='HTML'
        )
        logger.info("⏸️ Сканирование поставлено на паузу по команде /pause")
    
    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /resume - возобновить сканирование"""
        if not self.is_scanning:
            await update.message.reply_text(
                "⚠️ Сканирование остановлено.\n"
                "Используйте /start для запуска.",
                parse_mode='HTML'
            )
            return
        
        if not self.is_paused:
            await update.message.reply_text(
                "▶️ Сканирование УЖЕ активно.\n"
                "Для остановки используйте /stop или /pause",
                parse_mode='HTML'
            )
            return
        
        self.is_paused = False
        if self.detector:
            self.detector.resume()
        
        await update.message.reply_text(
            "▶️ <b>Сканирование ВОЗОБНОВЛЕНО!</b>\n\n"
            "🔍 Бот снова сканирует рынок...",
            parse_mode='HTML'
        )
        logger.info("▶️ Сканирование возобновлено по команде /resume")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /status - показывает статус"""
        if not self.is_scanning:
            status_text = "⏹️ ОСТАНОВЛЕН"
        elif self.is_paused:
            status_text = "⏸️ НА ПАУЗЕ"
        else:
            status_text = "✅ АКТИВЕН"
        
        await update.message.reply_text(
            f"📊 <b>СТАТУС БОТА</b>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"📈 Статус сканирования: {status_text}\n"
            f"⏱️ Интервал: {config.CHECK_INTERVAL} сек\n"
            f"🎯 Порог Стадии 1: 50/130\n"
            f"🎯 Порог Стадии 2: 70/130\n"
            f"📊 Максимум монет: {config.MAX_SYMBOLS}\n\n"
            f"📊 <b>Двухстадийная система:</b>\n"
            f"🟡 Стадия 1 — Раннее предупреждение\n"
            f"🟢 Стадия 2 — Памп/Дамп подтвержден\n\n"
            f"🎯 <b>Направление:</b>\n"
            f"🟢 LONG — памп вверх\n"
            f"🔴 SHORT — дамп вниз\n\n"
            f"📊 <b>Индикаторы:</b>\n"
            f"• OI 5/15/30 мин\n"
            f"• CVD (дельта)\n"
            f"• Bid/Ask дисбаланс (Top 25)\n"
            f"• Ускорение цены (вверх)\n"
            f"• Ликвидации\n"
            f"• Синергия Volume+OI\n"
            f"• Реальный Trade Count (WebSocket)\n\n"
            f"📱 Команды:\n"
            f"/start - Запустить\n"
            f"/stop - Остановить\n"
            f"/pause - Поставить на паузу\n"
            f"/resume - Возобновить\n"
            f"/status - Статус\n"
            f"/help - Помощь",
            parse_mode='HTML'
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - показывает помощь"""
        await update.message.reply_text(
            "❓ <b>ПОМОЩЬ</b>\n\n"
            "📌 <b>Что делает бот?</b>\n"
            "Сканирует Bybit и ищет пампы (LONG) и дампы (SHORT).\n\n"
            "📌 <b>Двухстадийная система:</b>\n"
            "🟡 <b>Стадия 1 — Раннее предупреждение</b>\n"
            "• Объём и OI растут\n"
            "• Цена ещё не ушла (< 2%)\n"
            "• Появляются агрессивные покупки/продажи\n"
            "• Баллы: 50-69\n\n"
            "🟢 <b>Стадия 2 — Памп/Дамп подтвержден</b>\n"
            "• Цена пробила (> 2%)\n"
            "• Объём высокий (> 2x)\n"
            "• OI растёт (> 5%)\n"
            "• Все индикаторы подтверждают\n"
            "• Баллы: 70+\n\n"
            "📌 <b>Направление:</b>\n"
            "🟢 <b>LONG</b> — памп вверх (бычий сигнал)\n"
            "🔴 <b>SHORT</b> — дамп вниз (медвежий сигнал)\n\n"
            "📌 <b>Индикаторы:</b>\n"
            "• 📈 OI за 5/15/30 минут (до 25 баллов)\n"
            "• 📉 CVD (дельта покупок/продаж) (до 15 баллов)\n"
            "• 📊 Bid/Ask дисбаланс (Top 25) (до 10 баллов)\n"
            "• ⚡ Ускорение цены (только вверх) (до 10 баллов)\n"
            "• 🔥 Ликвидации шортов/лонгов (до 15 баллов)\n"
            "• 🤝 Синергия объёма и OI (до 10 баллов)\n"
            "• 📊 Реальный Trade Count (WebSocket) (до 5 баллов)\n\n"
            "📌 <b>Команды:</b>\n"
            "/start  - Запустить сканирование\n"
            "/stop   - Остановить сканирование\n"
            "/pause  - Поставить на паузу (временная остановка)\n"
            "/resume - Возобновить работу после паузы\n"
            "/status - Показать статус\n"
            "/help   - Эта справка\n\n"
            "📌 <b>Как работают сигналы?</b>\n"
            "Каждые 5 минут бот проверяет монеты.\n"
            "Если находит сигнал - присылает <b>СО ЗВУКОМ</b> 🔔\n"
            "Если сигналов нет - присылает <b>БЕЗ ЗВУКА</b> 📊\n\n"
            "⚠️ <i>Торговля криптовалютами связана с высоким риском.\n"
            "Все решения принимайте на свой страх и риск.</i>",
            parse_mode='HTML'
        )
    
    async def _run_scanning(self):
        """Фоновое сканирование"""
        logger.info("🔄 Запущено фоновое сканирование")
        
        while self.is_scanning and self.detector:
            try:
                # Проверяем паузу
                if self.is_paused:
                    await asyncio.sleep(1)
                    continue
                
                logger.info("🔍 Начинаем сканирование...")
                
                # Используем асинхронное сканирование
                if hasattr(self.detector, 'scan_all_symbols_async'):
                    signals = await self.detector.scan_all_symbols_async()
                else:
                    signals = self.detector.scan_all_symbols()
                
                if signals:
                    await self.send_top_signals(signals)
                else:
                    await self.send_scan_status(0)
                
                # Ждём до следующего сканирования
                for _ in range(config.CHECK_INTERVAL):
                    if not self.is_scanning or self.is_paused:
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
        pause_text = " ⏸️ (на паузе)" if self.is_paused else ""
        message = f"""
📊 <b>Сканирование завершено</b>{pause_text}
🕐 {datetime.now().strftime('%H:%M:%S')}

📈 Найдено сигналов: <b>{signals_count}</b>
{'🔍 Продолжаем мониторинг...' if signals_count == 0 else '🚀 Есть потенциальные сигналы!'}
"""
        await self.send_message(message, silent=True)
    
    async def send_top_signals(self, signals):
        """Отправка сигналов (СО ЗВУКОМ) с двухстадийной системой и направлением"""
        await self.send_scan_status(len(signals))
        
        message = f"""
🔔🔊 <b>ВНИМАНИЕ! ОБНАРУЖЕНЫ СИГНАЛЫ!</b>

🚀 <b>ТОП-{min(len(signals), config.TOP_SIGNALS)} СИГНАЛОВ</b>
📅 {datetime.now().strftime('%H:%M:%S')}
📊 Всего найдено: {len(signals)}

"""
        
        for i, signal in enumerate(signals[:config.TOP_SIGNALS], 1):
            # Определяем стадию
            stage_emoji = "🟢" if signal.get('stage', 0) == 2 else "🟡"
            stage_text = signal.get('stage_message', '')
            
            # Определяем направление
            direction = signal.get('direction', 'NEUTRAL')
            if direction == "LONG":
                direction_emoji = "🟢"
                direction_text = "LONG (памп вверх)"
            elif direction == "SHORT":
                direction_emoji = "🔴"
                direction_text = "SHORT (дамп вниз)"
            else:
                direction_emoji = "⚪"
                direction_text = "NEUTRAL"
            
            # Определяем вероятность
            if signal['score'] >= 80:
                prob = "🔴 ВЫСОКАЯ"
                star = "⭐"
            elif signal['score'] >= 65:
                prob = "🟡 СРЕДНЯЯ"
                star = "🌟"
            else:
                prob = "🟢 НИЗКАЯ"
                star = "💫"
            
            # Синергия
            synergy_text = "✅" if signal.get('synergy', False) else "❌"
            
            # Trade Count
            trade_text = f"{signal.get('trade_growth', 1):.1f}x" if signal.get('trade_growth') else "Н/Д"
            
            # Ликвидации
            liq_text = ""
            liq_short = signal.get('liq_short', 0)
            liq_long = signal.get('liq_long', 0)
            if liq_short > liq_long * 1.5:
                liq_text = "🟢 Шортов больше (бычий)"
            elif liq_long > liq_short * 1.5:
                liq_text = "🔴 Лонгов больше (медвежий)"
            
            # Дополнительная информация о стадии
            stage_info = ""
            if signal.get('stage', 0) == 1:
                if direction == "LONG":
                    stage_info = "📌 Объём и OI растут, цена готовится к пробою ВВЕРХ"
                elif direction == "SHORT":
                    stage_info = "📌 Объём и OI растут, цена готовится к пробою ВНИЗ"
                else:
                    stage_info = "📌 Объём и OI растут, направление уточняется"
            elif signal.get('stage', 0) == 2:
                if direction == "LONG":
                    stage_info = "📌 ПАМП ПОДТВЕРЖДЕН! Движение вверх 🚀"
                elif direction == "SHORT":
                    stage_info = "📌 ДАМП ПОДТВЕРЖДЕН! Движение вниз 💥"
                else:
                    stage_info = "📌 Движение подтверждено, направление уточняется"
            
            message += f"""
{stage_emoji} <b>#{i} {signal['symbol']}</b> — {stage_text}
┌─────────────────────────────────────
│ 📊 Рейтинг: <b>{signal['score']}/130</b> | {prob} | {star}
│ 🎯 Направление: {direction_emoji} <b>{direction_text}</b>
│ 📈 Цена: {signal['price_change']:+.2f}%
│ 📊 Объём: {signal['volume_ratio']:.1f}x
│ 💰 OI: +{signal['oi_change']:.1f}%
│ 📉 CVD: {signal.get('cvd', 0):.0f}
│ 📊 Bid/Ask: {signal.get('bid_imbalance', 0):.1f}%
│ ⚡ Ускорение: {signal.get('acceleration', 1):.1f}x
│ 📊 Trade Count: {trade_text}
│ 🔥 Ликвидации: ${signal.get('liq_total', 0)/1e6:.2f}M {liq_text}
│ 📉 До сопротивления: {signal['resistance_gap']:.1f}%
│ 🤝 Синергия Volume+OI: {synergy_text}
│ 📌 {stage_info}
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
            
            # Удаляем старые обновления
            await self.bot.delete_webhook(drop_pending_updates=True)
            
            self.application = Application.builder().token(config.TELEGRAM_TOKEN).build()
            
            # ============================================================
            # РЕГИСТРИРУЕМ ВСЕ КОМАНДЫ
            # ============================================================
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("stop", self.stop_command))
            self.application.add_handler(CommandHandler("pause", self.pause_command))
            self.application.add_handler(CommandHandler("resume", self.resume_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            # ============================================================
            
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                timeout=30
            )
            
            logger.info("✅ Telegram бот запущен! Команды: /start, /stop, /pause, /resume, /status, /help")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telegram бота: {e}")
            return False
    
    async def stop_bot(self):
        """Остановка Telegram бота"""
        self.is_scanning = False
        self.is_paused = False
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