from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
from config import config
import logging
from datetime import datetime
import asyncio
from src.utils import signals_history

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
        self.last_signals = []
        self.last_scan_time = None
        self.pending_callbacks = {}
        self.subscribed_users = set()  # ← СПИСОК ВСЕХ ПОЛЬЗОВАТЕЛЕЙ
        logger.info("Telegram бот инициализирован")
    
    def set_detector(self, detector):
        self.detector = detector
    
    def _get_chat_id(self, update: Update):
        if update.callback_query:
            return update.callback_query.message.chat_id
        elif update.message:
            return update.message.chat_id
        return None
    
    def _add_user(self, chat_id):
        """Добавляет пользователя в список подписанных"""
        if chat_id not in self.subscribed_users:
            self.subscribed_users.add(chat_id)
            logger.info(f"✅ Пользователь {chat_id} подписан на сигналы")
            return True
        return False
    
    def _remove_user(self, chat_id):
        """Удаляет пользователя из списка подписанных"""
        if chat_id in self.subscribed_users:
            self.subscribed_users.remove(chat_id)
            logger.info(f"❌ Пользователь {chat_id} отписан от сигналов")
            return True
        return False
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start - запускает сканирование и подписывает на сигналы"""
        user = update.effective_user
        user_name = user.first_name if user.first_name else "Пользователь"
        chat_id = update.message.chat_id
        
        # Добавляем пользователя в список
        self._add_user(chat_id)
        
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
                f"📱 Команды:\n"
                f"/start - Запустить/подписаться\n"
                f"/stop - Остановить сканирование\n"
                f"/pause - Поставить на паузу\n"
                f"/resume - Возобновить работу\n"
                f"/result - Результаты последнего сканирования\n"
                f"/stats - Статистика сигналов\n"
                f"/status - Статус\n"
                f"/help - Помощь",
                parse_mode='HTML'
            )
            return
        
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
            f"🟢 Стадия 2 — Памп/Дамп подтвержден\n\n"
            f"✅ Вы подписаны на сигналы!\n"
            f"✅ Сканирование запущено!",
            parse_mode='HTML'
        )
        
        signals_history.set_user(chat_id)
        
        if self.detector:
            self.scan_task = asyncio.create_task(self._run_scanning())
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stop - останавливает сканирование и отписывает"""
        chat_id = update.message.chat_id
        
        if not self.is_scanning:
            await update.message.reply_text("⚠️ Сканирование уже остановлено.")
            return
        
        self.is_scanning = False
        self.is_paused = False
        if self.scan_task:
            self.scan_task.cancel()
            self.scan_task = None
        
        if self.detector:
            self.detector.resume()
        
        # Очищаем список пользователей при полной остановке
        self.subscribed_users.clear()
        
        await update.message.reply_text(
            "🛑 <b>Сканирование ОСТАНОВЛЕНО!</b>\n\n"
            "Для запуска используйте /start",
            parse_mode='HTML'
        )
        logger.info("⏹️ Сканирование остановлено по команде /stop")
    
    async def send_message_to_user(self, chat_id, text, silent=False, reply_markup=None):
        """Отправка сообщения конкретному пользователю"""
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True,
                disable_notification=silent,
                reply_markup=reply_markup
            )
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка отправки пользователю {chat_id}: {e}")
            return False
    
    async def broadcast_message(self, text, silent=False, reply_markup=None):
        """Отправка сообщения ВСЕМ подписанным пользователям"""
        if not self.subscribed_users:
            logger.warning("⚠️ Нет подписанных пользователей")
            return False
        
        success_count = 0
        for chat_id in self.subscribed_users:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode='HTML',
                    disable_web_page_preview=True,
                    disable_notification=silent,
                    reply_markup=reply_markup
                )
                success_count += 1
                await asyncio.sleep(0.3)  # Небольшая задержка между отправками
            except Exception as e:
                logger.error(f"❌ Ошибка отправки пользователю {chat_id}: {e}")
        
        logger.info(f"✅ Сообщение отправлено {success_count} пользователям")
        return success_count > 0
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.message.chat_id
        signals_history.set_user(chat_id)
        stats_message = signals_history.get_stats_message()
        await update.message.reply_text(stats_message, parse_mode='HTML')
    
    async def result_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.last_scan_time is None:
            await update.message.reply_text(
                "📊 <b>Результаты сканирования</b>\n\n"
                "🔍 Сканирование ещё не проводилось.\n"
                "Дождитесь первого сканирования или запустите /start",
                parse_mode='HTML'
            )
            return
        
        last_scan_time = self.last_scan_time.strftime('%H:%M:%S')
        
        if not self.last_signals:
            await update.message.reply_text(
                f"📊 <b>Результаты последнего сканирования</b>\n"
                f"🕐 {last_scan_time}\n\n"
                f"📈 Найдено сигналов: <b>0</b>\n"
                f"🔍 Все тихо, пампа нет.",
                parse_mode='HTML'
            )
            return
        
        message = f"""
📊 <b>Результаты последнего сканирования</b>
🕐 {last_scan_time}

🚀 Найдено сигналов: <b>{len(self.last_signals)}</b>

"""
        
        for i, signal in enumerate(self.last_signals[:config.TOP_SIGNALS], 1):
            stage_emoji = "🟢" if signal.get('stage', 0) == 2 else "🟡"
            stage_text = signal.get('stage_message', '')
            
            direction = signal.get('direction', 'NEUTRAL')
            if direction == "LONG":
                direction_emoji = "🟢"
                direction_text = "LONG"
            elif direction == "SHORT":
                direction_emoji = "🔴"
                direction_text = "SHORT"
            else:
                direction_emoji = "⚪"
                direction_text = "NEUTRAL"
            
            message += f"""
{stage_emoji} <b>#{i} {signal['symbol']}</b> {stage_text}
🎯 {direction_emoji} {direction_text} | Рейтинг: {signal['score']}/130
📈 Цена: {signal['price_change']:+.2f}%
📊 Объём: {signal['volume_ratio']:.1f}x
💰 OI: +{signal['oi_change']:.1f}%
📉 CVD: {signal.get('cvd', 0):.0f}
📊 Bid/Ask: {signal.get('bid_imbalance', 0):.1f}%
⚡ Ускорение: {signal.get('acceleration', 1):.1f}x
📊 Trade Count: {signal.get('trade_growth', 1):.1f}x
─────────────────────
"""
        
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.is_scanning:
            status_text = "⏹️ ОСТАНОВЛЕН"
        elif self.is_paused:
            status_text = "⏸️ НА ПАУЗЕ"
        else:
            status_text = "✅ АКТИВЕН"
        
        last_scan = self.last_scan_time.strftime('%H:%M:%S') if self.last_scan_time else "Не было"
        signals_count = len(self.last_signals) if self.last_signals else 0
        users_count = len(self.subscribed_users)
        
        await update.message.reply_text(
            f"📊 <b>СТАТУС БОТА</b>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"📈 Статус сканирования: {status_text}\n"
            f"👥 Подписанных пользователей: {users_count}\n"
            f"⏱️ Интервал: {config.CHECK_INTERVAL} сек\n"
            f"🎯 Порог Стадии 1: 50/130\n"
            f"🎯 Порог Стадии 2: 70/130\n"
            f"📊 Максимум монет: {config.MAX_SYMBOLS}\n\n"
            f"📊 <b>Последнее сканирование:</b>\n"
            f"🕐 Время: {last_scan}\n"
            f"📈 Найдено сигналов: <b>{signals_count}</b>\n\n"
            f"📱 Команды:\n"
            f"/start - Запустить/подписаться\n"
            f"/stop - Остановить сканирование\n"
            f"/pause - Поставить на паузу\n"
            f"/resume - Возобновить\n"
            f"/result - Результаты последнего сканирования\n"
            f"/stats - Статистика сигналов\n"
            f"/status - Статус\n"
            f"/help - Помощь",
            parse_mode='HTML'
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "❓ <b>ПОМОЩЬ</b>\n\n"
            "📌 <b>Что делает бот?</b>\n"
            "Сканирует Bybit и ищет пампы (LONG) и дампы (SHORT).\n\n"
            "📌 <b>Двухстадийная система:</b>\n"
            "🟡 Стадия 1 — Раннее предупреждение (50-69 баллов)\n"
            "🟢 Стадия 2 — Памп/Дамп подтвержден (70+ баллов)\n\n"
            "📌 <b>Направление:</b>\n"
            "🟢 LONG — памп вверх\n"
            "🔴 SHORT — дамп вниз\n\n"
            "📌 <b>Обратная связь:</b>\n"
            "У каждого сигнала есть кнопки:\n"
            "✅ Отработал\n"
            "❌ Не отработал\n"
            "🗑️ Удалить\n\n"
            "📌 <b>Команды:</b>\n"
            "/start  - Запустить/подписаться на сигналы\n"
            "/stop   - Остановить сканирование\n"
            "/pause  - Поставить на паузу\n"
            "/resume - Возобновить работу\n"
            "/result - Результаты последнего сканирования\n"
            "/stats  - Статистика сигналов\n"
            "/status - Показать статус\n"
            "/help   - Эта справка",
            parse_mode='HTML'
        )
    
    async def _run_scanning(self):
        logger.info("🔄 Запущено фоновое сканирование")
        
        while self.is_scanning and self.detector:
            try:
                if self.is_paused:
                    await asyncio.sleep(1)
                    continue
                
                logger.info("🔍 Начинаем сканирование...")
                
                if hasattr(self.detector, 'scan_all_symbols_async'):
                    signals = await self.detector.scan_all_symbols_async()
                else:
                    signals = self.detector.scan_all_symbols()
                
                self.last_signals = signals if signals else []
                self.last_scan_time = datetime.now()
                logger.info(f"📊 Сохранено {len(self.last_signals)} сигналов")
                
                if signals:
                    # Отправляем сигналы ВСЕМ подписанным пользователям
                    await self.broadcast_signals(signals)
                    logger.info(f"✅ Отправлено {len(signals)} сигналов всем пользователям")
                else:
                    logger.info("ℹ️ Сигналов не найдено (тишина)")
                
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
    
    async def broadcast_signals(self, signals):
        """Отправка сигналов ВСЕМ подписанным пользователям"""
        for signal in signals[:config.TOP_SIGNALS]:
            # Сохраняем сигнал для каждого пользователя
            signal_data = signal.copy()
            
            # Формируем сообщение
            message = self._format_signal_message(signal)
            
            # Отправляем всем пользователям
            for chat_id in self.subscribed_users:
                # Сохраняем историю для каждого пользователя
                signals_history.set_user(chat_id)
                signal_id = signals_history.add_signal(signal_data)
                
                keyboard = [
                    [
                        InlineKeyboardButton("✅ Отработал", callback_data=f"confirm_{signal_id}"),
                        InlineKeyboardButton("❌ Не отработал", callback_data=f"fail_{signal_id}"),
                        InlineKeyboardButton("🗑️ Удалить", callback_data=f"delete_{signal_id}")
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await self.send_message_to_user(
                    chat_id,
                    message,
                    silent=False,
                    reply_markup=reply_markup
                )
                await asyncio.sleep(0.3)
    
    def _format_signal_message(self, signal):
        """Форматирует сообщение с сигналом"""
        stage_emoji = "🟢" if signal.get('stage', 0) == 2 else "🟡"
        stage_text = signal.get('stage_message', '')
        
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
        
        if signal['score'] >= 80:
            prob = "🔴 ВЫСОКАЯ"
            star = "⭐"
        elif signal['score'] >= 65:
            prob = "🟡 СРЕДНЯЯ"
            star = "🌟"
        else:
            prob = "🟢 НИЗКАЯ"
            star = "💫"
        
        synergy_text = "✅" if signal.get('synergy', False) else "❌"
        trade_text = f"{signal.get('trade_growth', 1):.1f}x" if signal.get('trade_growth') else "Н/Д"
        
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
        
        return f"""
🔔🔊 <b>ВНИМАНИЕ! ОБНАРУЖЕН СИГНАЛ!</b>

{stage_emoji} <b>{signal['symbol']}</b> — {stage_text}
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
│ 📉 До сопротивления: {signal['resistance_gap']:.1f}%
│ 🤝 Синергия Volume+OI: {synergy_text}
│ 📌 {stage_info}
└─────────────────────────────────────

📌 <b>Оцените сигнал:</b>
"""
    
    async def handle_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        chat_id = query.message.chat_id
        
        signals_history.set_user(chat_id)
        
        if query.message.message_id in self.pending_callbacks:
            await query.answer("⏳ Обработка...", show_alert=False)
            return
        
        self.pending_callbacks[query.message.message_id] = True
        await query.answer()
        
        try:
            data = query.data
            
            if data.startswith("confirm_"):
                signal_id = int(data.split("_")[1])
                status = "confirmed"
                emoji = "✅"
                status_text = "Отработал"
            elif data.startswith("fail_"):
                signal_id = int(data.split("_")[1])
                status = "failed"
                emoji = "❌"
                status_text = "Не отработал"
            elif data.startswith("delete_"):
                signal_id = int(data.split("_")[1])
                status = "deleted"
                emoji = "🗑️"
                status_text = "Удалён"
            else:
                await query.edit_message_text("❌ Неизвестная команда")
                return
            
            success, msg = signals_history.update_signal_status(signal_id, status)
            
            if success:
                stats = signals_history.get_stats()
                accuracy = stats['accuracy']
                
                if accuracy >= 70:
                    accuracy_emoji = "🟢"
                elif accuracy >= 50:
                    accuracy_emoji = "🟡"
                else:
                    accuracy_emoji = "🔴"
                
                new_text = query.message.text + f"\n\n{emoji} <b>Вы оценили сигнал как: {status_text}</b>"
                
                if status != "deleted":
                    new_text += f"\n📊 Текущая точность: {accuracy_emoji} {accuracy}%"
                else:
                    new_text += f"\n📊 Сигнал удалён из статистики"
                
                await query.edit_message_text(
                    new_text,
                    parse_mode='HTML',
                    reply_markup=None
                )
                
                logger.info(f"📊 Пользователь {chat_id} оценил сигнал #{signal_id} как {status_text}")
            else:
                await query.edit_message_text(f"⚠️ {msg}")
                
        finally:
            if query.message.message_id in self.pending_callbacks:
                del self.pending_callbacks[query.message.message_id]
    
    async def run_bot(self):
        try:
            logger.info("🔄 Запускаем Telegram бота...")
            
            await self.bot.delete_webhook(drop_pending_updates=True)
            
            self.application = Application.builder().token(config.TELEGRAM_TOKEN).build()
            
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("stop", self.stop_command))
            self.application.add_handler(CommandHandler("pause", self.pause_command))
            self.application.add_handler(CommandHandler("resume", self.resume_command))
            self.application.add_handler(CommandHandler("result", self.result_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            
            self.application.add_handler(CallbackQueryHandler(self.handle_feedback))
            
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                timeout=30
            )
            
            logger.info("✅ Telegram бот запущен!")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telegram бота: {e}")
            return False
    
    async def stop_bot(self):
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