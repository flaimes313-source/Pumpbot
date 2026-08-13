from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from config import config
import logging
from datetime import datetime
import asyncio
from src.utils import signals_history, subscribers_manager

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
        self.admin_states = {}
        logger.info("Telegram бот инициализирован")
    
    def set_detector(self, detector):
        self.detector = detector
    
    def _add_user(self, update: Update):
        """
        Добавляет пользователя в подписчики с сохранением в файл.
        Новые пользователи добавляются с is_blocked = True (автоблокировка).
        """
        chat_id = update.effective_chat.id
        user = update.effective_user
        
        username = user.username if user.username else None
        first_name = user.first_name if user.first_name else None
        last_name = user.last_name if user.last_name else None
        
        if subscribers_manager.is_subscribed(chat_id):
            subscribers_manager.add_subscriber(chat_id, username, first_name, last_name)
            logger.info(f"🔄 Обновлена подписка: @{username or chat_id}")
            return False
        
        subscribers_manager.add_subscriber(chat_id, username, first_name, last_name)
        subscribers_manager.block_subscriber(chat_id)
        logger.info(f"🚫 Новый пользователь @{username or chat_id} добавлен с автоблокировкой")
        return True
    
    # ============================================================
    # АДМИН-ПАНЕЛЬ
    # ============================================================
    
    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /admin - показывает админ-панель"""
        chat_id = update.message.chat_id
        
        if str(chat_id) != str(self.chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        keyboard = [
            [
                InlineKeyboardButton("📋 Список пользователей", callback_data="admin_users"),
                InlineKeyboardButton("➕ Добавить пользователя", callback_data="admin_add")
            ],
            [
                InlineKeyboardButton("➖ Удалить пользователя", callback_data="admin_remove"),
                InlineKeyboardButton("🚫 Заблокировать", callback_data="admin_block")
            ],
            [
                InlineKeyboardButton("✅ Разблокировать", callback_data="admin_unblock"),
                InlineKeyboardButton("📨 Рассылка", callback_data="admin_broadcast")
            ],
            [
                InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📊 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
            "Выберите действие:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def admin_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатий кнопок в админ-панели"""
        query = update.callback_query
        chat_id = query.message.chat_id
        
        if str(chat_id) != str(self.chat_id):
            await query.answer("⛔ Доступ запрещён.", show_alert=True)
            return
        
        await query.answer()
        action = query.data
        
        if action == "admin_users":
            await self._show_users(query)
        
        elif action == "admin_add":
            await self._ask_add_user(query)
        
        elif action == "admin_remove":
            await self._ask_remove_user(query)
        
        elif action == "admin_block":
            await self._ask_block_user(query)
        
        elif action == "admin_unblock":
            await self._ask_unblock_user(query)
        
        elif action == "admin_broadcast":
            await self._ask_broadcast(query)
        
        elif action == "admin_stats":
            await self._show_stats(query)
        
        elif action == "admin_back":
            await self._admin_back(query)
    
    # ============================================================
    # МЕТОДЫ АДМИН-ПАНЕЛИ
    # ============================================================
    
    async def _show_users(self, query):
        """Показывает список пользователей"""
        subscribers = subscribers_manager.get_subscribers()
        
        if not subscribers:
            await query.edit_message_text(
                "📊 <b>Список подписчиков</b>\n\nНет подписанных пользователей.",
                parse_mode='HTML'
            )
            return
        
        message = "📊 <b>Список подписчиков</b>\n\n"
        
        for chat_id_str, data in subscribers.items():
            username = data.get('username', 'unknown')
            first_name = data.get('first_name', 'unknown')
            subscribed_at = data.get('subscribed_at', 'unknown')[:16]
            is_blocked = data.get('is_blocked', False)
            
            status = "🔴 ЗАБЛОКИРОВАН" if is_blocked else "🟢 АКТИВЕН"
            
            message += f"👤 @{username} ({first_name})\n"
            message += f"   🆔 {chat_id_str}\n"
            message += f"   📅 {subscribed_at}\n"
            message += f"   📊 {status}\n\n"
        
        message += f"\n📊 Всего: {len(subscribers)} пользователей"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def _ask_add_user(self, query):
        """Запрашивает chat_id для добавления"""
        self.admin_states[query.message.chat_id] = 'add_user'
        
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "➕ <b>Добавление пользователя</b>\n\n"
            "Введите <b>chat_id</b> или <b>@username</b> пользователя.\n\n"
            "Пользователь будет автоматически разблокирован.\n\n"
            "Пример: <code>123456789</code> или <code>@username</code>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def _ask_remove_user(self, query):
        """Запрашивает chat_id для удаления"""
        self.admin_states[query.message.chat_id] = 'remove_user'
        
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "➖ <b>Удаление пользователя</b>\n\n"
            "Введите <b>chat_id</b> пользователя для удаления.\n\n"
            "Пример: <code>123456789</code>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def _ask_block_user(self, query):
        """Запрашивает chat_id для блокировки"""
        self.admin_states[query.message.chat_id] = 'block_user'
        
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🚫 <b>Блокировка пользователя</b>\n\n"
            "Введите <b>chat_id</b> пользователя для блокировки.\n\n"
            "Заблокированный пользователь НЕ будет получать сигналы.\n\n"
            "Пример: <code>123456789</code>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def _ask_unblock_user(self, query):
        """Запрашивает chat_id для разблокировки"""
        self.admin_states[query.message.chat_id] = 'unblock_user'
        
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ <b>Разблокировка пользователя</b>\n\n"
            "Введите <b>chat_id</b> пользователя для разблокировки.\n\n"
            "Пример: <code>123456789</code>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def _ask_broadcast(self, query):
        """Запрашивает сообщение для рассылки"""
        self.admin_states[query.message.chat_id] = 'broadcast'
        
        keyboard = [[InlineKeyboardButton("🔙 Отмена", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📨 <b>Рассылка сообщения</b>\n\n"
            "Введите текст сообщения для рассылки <b>ВСЕМ</b> подписанным пользователям.\n\n"
            "Пример: <i>Всем привет! Бот обновлён.</i>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def _show_stats(self, query):
        """Показывает статистику бота (только для админа)"""
        subscribers_count = subscribers_manager.get_subscribers_count()
        signals_count = len(self.last_signals) if self.last_signals else 0
        last_scan = self.last_scan_time.strftime('%H:%M:%S') if self.last_scan_time else "Не было"
        
        message = f"""
📊 <b>СТАТИСТИКА БОТА</b>

👥 Подписанных пользователей: {subscribers_count}
📈 Сигналов за последнее сканирование: {signals_count}
🕐 Последнее сканирование: {last_scan}
⏱️ Интервал сканирования: {config.CHECK_INTERVAL} сек
🎯 Порог срабатывания: {config.SCORE_THRESHOLD}/130
📊 Максимум монет: {config.MAX_SYMBOLS}
"""
        
        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="admin_back")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def _admin_back(self, query):
        """Возврат в админ-панель"""
        keyboard = [
            [
                InlineKeyboardButton("📋 Список пользователей", callback_data="admin_users"),
                InlineKeyboardButton("➕ Добавить пользователя", callback_data="admin_add")
            ],
            [
                InlineKeyboardButton("➖ Удалить пользователя", callback_data="admin_remove"),
                InlineKeyboardButton("🚫 Заблокировать", callback_data="admin_block")
            ],
            [
                InlineKeyboardButton("✅ Разблокировать", callback_data="admin_unblock"),
                InlineKeyboardButton("📨 Рассылка", callback_data="admin_broadcast")
            ],
            [
                InlineKeyboardButton("📊 Статистика бота", callback_data="admin_stats")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📊 <b>АДМИН-ПАНЕЛЬ</b>\n\n"
            "Выберите действие:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # ============================================================
    # ОБРАБОТКА СООБЩЕНИЙ ОТ АДМИНА (для ввода данных)
    # ============================================================
    
    async def handle_admin_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений от админа (для диалогов)"""
        chat_id = update.message.chat_id
        
        if str(chat_id) != str(self.chat_id):
            return
        
        if chat_id not in self.admin_states:
            return
        
        state = self.admin_states[chat_id]
        text = update.message.text.strip()
        
        if state == 'add_user':
            await self._process_add_user(update, text)
        
        elif state == 'remove_user':
            await self._process_remove_user(update, text)
        
        elif state == 'block_user':
            await self._process_block_user(update, text)
        
        elif state == 'unblock_user':
            await self._process_unblock_user(update, text)
        
        elif state == 'broadcast':
            await self._process_broadcast(update, text)
        
        del self.admin_states[chat_id]
    
    async def _process_add_user(self, update, text):
        """Обработка добавления пользователя (с автоматической разблокировкой)"""
        chat_id = update.message.chat_id
        
        try:
            if text.startswith('@'):
                username = text[1:]
                try:
                    user = await self.bot.get_chat(text)
                    user_chat_id = user.id
                except Exception as e:
                    await update.message.reply_text(
                        f"❌ Не удалось найти пользователя {text}.\n\n"
                        f"Убедитесь, что пользователь существует.\n"
                        f"Или введите chat_id (число)."
                    )
                    return
            else:
                user_chat_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Введите chat_id (число) или @username.")
            return
        
        if not subscribers_manager.is_subscribed(user_chat_id):
            subscribers_manager.add_subscriber(user_chat_id)
        
        subscribers_manager.unblock_subscriber(user_chat_id)
        
        await update.message.reply_text(
            f"✅ Пользователь {user_chat_id} добавлен и РАЗБЛОКИРОВАН!\n\n"
            f"Теперь он будет получать сигналы."
        )
    
    async def _process_remove_user(self, update, text):
        """Обработка удаления пользователя"""
        try:
            user_chat_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Введите chat_id (число).")
            return
        
        if subscribers_manager.remove_subscriber(user_chat_id):
            await update.message.reply_text(f"✅ Пользователь {user_chat_id} удалён из подписчиков")
        else:
            await update.message.reply_text(f"⚠️ Пользователь {user_chat_id} не найден")
    
    async def _process_block_user(self, update, text):
        """Обработка блокировки пользователя"""
        try:
            user_chat_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Введите chat_id (число).")
            return
        
        if subscribers_manager.block_subscriber(user_chat_id):
            await update.message.reply_text(f"🚫 Пользователь {user_chat_id} заблокирован (сигналы не приходят)")
        else:
            await update.message.reply_text(f"⚠️ Пользователь {user_chat_id} не найден")
    
    async def _process_unblock_user(self, update, text):
        """Обработка разблокировки пользователя"""
        try:
            user_chat_id = int(text)
        except ValueError:
            await update.message.reply_text("❌ Неверный формат. Введите chat_id (число).")
            return
        
        if subscribers_manager.unblock_subscriber(user_chat_id):
            await update.message.reply_text(f"✅ Пользователь {user_chat_id} разблокирован (сигналы снова приходят)")
        else:
            await update.message.reply_text(f"⚠️ Пользователь {user_chat_id} не найден")
    
    async def _process_broadcast(self, update, text):
        """Обработка рассылки"""
        chat_id = update.message.chat_id
        message_text = text
        
        subscribers = subscribers_manager.get_all_subscribers_list()
        
        if not subscribers:
            await update.message.reply_text("⚠️ Нет подписанных пользователей для рассылки.")
            return
        
        await update.message.reply_text(
            f"📨 <b>Начинаю рассылку</b>\n\n"
            f"👥 Получателей: {len(subscribers)}\n"
            f"📝 Сообщение: {message_text}\n\n"
            f"⏳ Идёт отправка...",
            parse_mode='HTML'
        )
        
        success_count = 0
        fail_count = 0
        
        for user_chat_id in subscribers:
            try:
                await self.bot.send_message(
                    chat_id=user_chat_id,
                    text=f"📢 <b>Сообщение от администратора</b>\n\n{message_text}",
                    parse_mode='HTML'
                )
                success_count += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                fail_count += 1
                logger.error(f"❌ Ошибка отправки пользователю {user_chat_id}: {e}")
        
        await update.message.reply_text(
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"📨 Успешно доставлено: {success_count}\n"
            f"❌ Не доставлено: {fail_count}\n"
            f"👥 Всего получателей: {len(subscribers)}",
            parse_mode='HTML'
        )
        
        logger.info(f"📨 Рассылка завершена: {success_count} успешно, {fail_count} ошибок")
    
    # ============================================================
    # ОСНОВНЫЕ КОМАНДЫ
    # ============================================================
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /start - запускает сканирование и подписывает на сигналы"""
        user = update.effective_user
        user_name = user.first_name if user.first_name else "Пользователь"
        chat_id = update.message.chat_id
        
        self._add_user(update)
        
        if subscribers_manager.is_blocked(chat_id):
            await update.message.reply_text(
                f"👋 Привет, {user_name}!\n\n"
                f"⛔ <b>Ваш аккаунт ожидает подтверждения.</b>\n\n"
                f"Администратор получил уведомление о вашем запросе.\n"
                f"После подтверждения вы будете получать сигналы.\n\n"
                f"⏳ Пожалуйста, подождите.",
                parse_mode='HTML'
            )
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=f"🆕 <b>Новый пользователь ожидает подтверждения!</b>\n\n"
                     f"👤 Имя: {user_name}\n"
                     f"🆔 ID: {chat_id}\n"
                     f"👤 Username: @{user.username if user.username else 'Нет'}\n\n"
                     f"Для активации используйте:\n"
                     f"<code>/add_user {chat_id}</code>\n"
                     f"или\n"
                     f"<code>/add_user @{user.username if user.username else ''}</code>",
                parse_mode='HTML'
            )
            return
        
        if self.is_scanning:
            status_text = "⏸️ НА ПАУЗЕ" if self.is_paused else "✅ АКТИВЕН"
            await update.message.reply_text(
                f"👋 Привет, {user_name}!\n\n"
                f"✅ Сканирование УЖЕ запущено!\n"
                f"📊 Статус: {status_text}\n"
                f"🔄 Бот работает в фоновом режиме.\n\n"
                f"✅ Вы подписаны на сигналы!\n\n"
                f"📱 Команды:\n"
                f"/start - Запустить/подписаться\n"
                f"/stop - Остановить сканирование\n"
                f"/pause - Поставить на паузу\n"
                f"/resume - Возобновить работу\n"
                f"/support - Контакты поддержки\n"
                f"/help - Помощь",
                parse_mode='HTML'
            )
            return
        
        self.is_scanning = True
        self.is_paused = False
        
        await update.message.reply_text(
            f"👋 Привет, {user_name}!\n\n"
            f"🚀 <b>ЗАПУСКАЮ СКАНИРОВАНИЕ...</b>\n\n"
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
            f"✅ <b>Вы подписаны на сигналы!</b>\n"
            f"✅ <b>Сканирование запущено!</b>\n\n"
            f"📱 <b>Команды:</b>\n"
            f"/start - Запустить/подписаться\n"
            f"/stop - Остановить сканирование\n"
            f"/pause - Поставить на паузу\n"
            f"/resume - Возобновить работу\n"
            f"/support - Контакты поддержки\n"
            f"/help - Помощь\n\n"
            f"⚠️ <i>Бот предоставляет информационно-аналитические материалы и не является инвестиционным советником. Сигналы не являются индивидуальными инвестиционными рекомендациями. Решение о совершении сделки пользователь принимает самостоятельно. Торговля криптовалютами связана с высоким риском потери капитала.</i>",
            parse_mode='HTML'
        )
        
        signals_history.set_user(chat_id)
        
        if self.detector:
            self.scan_task = asyncio.create_task(self._run_scanning())
    
    async def stop_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stop - останавливает сканирование"""
        chat_id = update.message.chat_id
        
        # Проверяем, разблокирован ли пользователь
        if subscribers_manager.is_blocked(chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
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
        
        await update.message.reply_text(
            "🛑 <b>Сканирование ОСТАНОВЛЕНО!</b>\n\n"
            "Для запуска используйте /start",
            parse_mode='HTML'
        )
        logger.info("⏹️ Сканирование остановлено по команде /stop")
    
    async def pause_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /pause - поставить сканирование на паузу"""
        chat_id = update.message.chat_id
        
        if subscribers_manager.is_blocked(chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        if not self.is_scanning:
            await update.message.reply_text(
                "⚠️ Сканирование не запущено.\nИспользуйте /start для запуска.",
                parse_mode='HTML'
            )
            return
        
        if self.is_paused:
            await update.message.reply_text(
                "⏸️ Сканирование УЖЕ на паузе.\nДля возобновления используйте /resume",
                parse_mode='HTML'
            )
            return
        
        self.is_paused = True
        if self.detector:
            self.detector.pause()
        
        await update.message.reply_text(
            "⏸️ <b>Сканирование поставлено на ПАУЗУ!</b>\n\n"
            "▶️ Для возобновления используйте /resume",
            parse_mode='HTML'
        )
        logger.info("⏸️ Сканирование поставлено на паузу по команде /pause")
    
    async def resume_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /resume - возобновить сканирование"""
        chat_id = update.message.chat_id
        
        if subscribers_manager.is_blocked(chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        if not self.is_scanning:
            await update.message.reply_text(
                "⚠️ Сканирование остановлено.\nИспользуйте /start для запуска.",
                parse_mode='HTML'
            )
            return
        
        if not self.is_paused:
            await update.message.reply_text(
                "▶️ Сканирование УЖЕ активно.\nДля остановки используйте /stop или /pause",
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
    
    async def support_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /support - показывает контакты поддержки (доступна всем)"""
        keyboard = [
            [
                InlineKeyboardButton("👤 Админ @Linga3444", url="https://t.me/Linga3444"),
                InlineKeyboardButton("👤 Админ @testirovshikii", url="https://t.me/testirovshikii")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "📞 <b>Поддержка</b>\n\n"
            "По всем вопросам обращайтесь к администраторам:\n\n"
            "👤 <b>@Linga3444</b> — главный администратор\n"
            "👤 <b>@testirovshikii</b> — техническая поддержка\n\n"
            "Нажмите на имя, чтобы написать в Telegram.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    async def stats_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /stats - показывает статистику сигналов (только для разблокированных)"""
        chat_id = update.message.chat_id
        
        if subscribers_manager.is_blocked(chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        signals_history.set_user(chat_id)
        stats_message = signals_history.get_stats_message()
        await update.message.reply_text(stats_message, parse_mode='HTML')
    
    async def result_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /result - показывает результаты последнего сканирования (только для разблокированных)"""
        chat_id = update.message.chat_id
        
        if subscribers_manager.is_blocked(chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        if self.last_scan_time is None:
            await update.message.reply_text(
                "📊 <b>Результаты сканирования</b>\n\n"
                "🔍 Сканирование ещё не проводилось.\n"
                "Дождитесь первого сканирования.",
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
        """Команда /status - показывает статус бота (только для разблокированных)"""
        chat_id = update.message.chat_id
        
        if subscribers_manager.is_blocked(chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        if not self.is_scanning:
            status_text = "⏹️ ОСТАНОВЛЕН"
        elif self.is_paused:
            status_text = "⏸️ НА ПАУЗЕ"
        else:
            status_text = "✅ АКТИВЕН"
        
        last_scan = self.last_scan_time.strftime('%H:%M:%S') if self.last_scan_time else "Не было"
        signals_count = len(self.last_signals) if self.last_signals else 0
        
        await update.message.reply_text(
            f"📊 <b>СТАТУС БОТА</b>\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"📈 Статус сканирования: {status_text}\n"
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
            f"/support - Контакты поддержки\n"
            f"/help - Помощь",
            parse_mode='HTML'
        )
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /help - показывает помощь (доступна всем)"""
        chat_id = update.message.chat_id
        
        if subscribers_manager.is_blocked(chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
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
            "/support - Контакты поддержки\n"
            "/help   - Эта справка\n\n"
            "⚠️ <i>Бот предоставляет информационно-аналитические материалы и не является инвестиционным советником. Сигналы не являются индивидуальными инвестиционными рекомендациями. Решение о совершении сделки пользователь принимает самостоятельно. Торговля криптовалютами связана с высоким риском потери капитала.</i>",
            parse_mode='HTML'
        )
    
    async def _run_scanning(self):
        """Фоновое сканирование"""
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
    
    async def broadcast_signals(self, signals):
        """Отправка сигналов всем подписанным пользователям"""
        subscribers = subscribers_manager.get_subscribers_list()
        
        if not subscribers:
            logger.warning("⚠️ Нет активных подписанных пользователей")
            return
        
        logger.info(f"📊 Отправка сигналов {len(subscribers)} активным пользователям")
        
        for signal in signals[:config.TOP_SIGNALS]:
            signal_data = signal.copy()
            message = self._format_signal_message(signal)
            
            for chat_id in subscribers:
                try:
                    if subscribers_manager.is_blocked(chat_id):
                        logger.debug(f"⏭️ Пропуск заблокированного пользователя {chat_id}")
                        continue
                    
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
                    
                    await self.send_message_to_user(chat_id, message, silent=False, reply_markup=reply_markup)
                    await asyncio.sleep(0.3)
                except Exception as e:
                    logger.error(f"❌ Ошибка отправки пользователю {chat_id}: {e}")
    
    def _format_signal_message(self, signal):
        """Форматирует сообщение с сигналом (дисклеймер ПЕРЕД кнопками)"""
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

⚠️ <i>Бот предоставляет информационно-аналитические материалы и не является инвестиционным советником. Сигналы не являются индивидуальными инвестиционными рекомендациями. Решение о совершении сделки пользователь принимает самостоятельно. Торговля криптовалютами связана с высоким риском потери капитала.</i>

📌 <b>Оцените сигнал:</b>
"""
    
    async def handle_feedback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка нажатия на кнопки обратной связи"""
        query = update.callback_query
        chat_id = query.message.chat_id
        
        # Проверяем, разблокирован ли пользователь
        if subscribers_manager.is_blocked(chat_id):
            await query.answer("⛔ Доступ запрещён.", show_alert=True)
            return
        
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
        """Запуск Telegram бота с увеличенными таймаутами"""
        try:
            logger.info("🔄 Запускаем Telegram бота...")
            
            await self.bot.delete_webhook(drop_pending_updates=True)
            
            self.application = Application.builder() \
                .token(config.TELEGRAM_TOKEN) \
                .connect_timeout(60) \
                .read_timeout(60) \
                .write_timeout(60) \
                .build()
            
            # Основные команды (доступны только разблокированным)
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("stop", self.stop_command))
            self.application.add_handler(CommandHandler("pause", self.pause_command))
            self.application.add_handler(CommandHandler("resume", self.resume_command))
            self.application.add_handler(CommandHandler("result", self.result_command))
            self.application.add_handler(CommandHandler("stats", self.stats_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            
            # Команды доступные всем (включая заблокированных)
            self.application.add_handler(CommandHandler("support", self.support_command))
            
            # Админ-панель
            self.application.add_handler(CommandHandler("admin", self.admin_panel))
            self.application.add_handler(CallbackQueryHandler(self.admin_callback, pattern="^admin_"))
            
            # Обработчик текстовых сообщений для админ-диалогов
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_admin_message))
            
            # Обработчик для отмены диалога
            self.application.add_handler(CommandHandler("cancel", self._cancel_admin_dialog))
            
            self.application.add_handler(CallbackQueryHandler(self.handle_feedback))
            
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                timeout=60
            )
            
            logger.info("✅ Telegram бот запущен!")
            return True
        except Exception as e:
            logger.error(f"❌ Ошибка запуска Telegram бота: {e}")
            return False
    
    async def _cancel_admin_dialog(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Отмена текущего диалога"""
        chat_id = update.message.chat_id
        if chat_id in self.admin_states:
            del self.admin_states[chat_id]
            await update.message.reply_text("❌ Действие отменено.")
    
    # ============================================================
    # СТАРЫЕ АДМИН-КОМАНДЫ (оставлены для совместимости)
    # ============================================================
    
    async def add_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /add_user - добавляет пользователя вручную (только для админа)"""
        chat_id = update.message.chat_id
        
        if str(chat_id) != str(self.chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 Использование: /add_user <chat_id> [username]\n"
                "Пример: /add_user 123456789 @username"
            )
            return
        
        try:
            user_chat_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат chat_id")
            return
        
        username = args[1] if len(args) > 1 else None
        
        if subscribers_manager.add_subscriber(user_chat_id, username):
            subscribers_manager.unblock_subscriber(user_chat_id)
            await update.message.reply_text(f"✅ Пользователь {user_chat_id} добавлен и разблокирован")
        else:
            await update.message.reply_text(f"ℹ️ Пользователь {user_chat_id} уже в списке подписчиков")
            if subscribers_manager.is_blocked(user_chat_id):
                subscribers_manager.unblock_subscriber(user_chat_id)
                await update.message.reply_text(f"🔓 Пользователь {user_chat_id} разблокирован")
    
    async def remove_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /remove_user - удаляет пользователя (только для админа)"""
        chat_id = update.message.chat_id
        
        if str(chat_id) != str(self.chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 Использование: /remove_user <chat_id>\n"
                "Пример: /remove_user 123456789"
            )
            return
        
        try:
            user_chat_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат chat_id")
            return
        
        if subscribers_manager.remove_subscriber(user_chat_id):
            await update.message.reply_text(f"✅ Пользователь {user_chat_id} удалён из подписчиков")
        else:
            await update.message.reply_text(f"⚠️ Пользователь {user_chat_id} не найден")
    
    async def block_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /block_user - блокирует пользователя (только для админа)"""
        chat_id = update.message.chat_id
        
        if str(chat_id) != str(self.chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 Использование: /block_user <chat_id>\n"
                "Пример: /block_user 123456789"
            )
            return
        
        try:
            user_chat_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат chat_id")
            return
        
        if subscribers_manager.block_subscriber(user_chat_id):
            await update.message.reply_text(f"🚫 Пользователь {user_chat_id} заблокирован (сигналы не приходят)")
        else:
            await update.message.reply_text(f"⚠️ Пользователь {user_chat_id} не найден")
    
    async def unblock_user_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /unblock_user - разблокирует пользователя (только для админа)"""
        chat_id = update.message.chat_id
        
        if str(chat_id) != str(self.chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 Использование: /unblock_user <chat_id>\n"
                "Пример: /unblock_user 123456789"
            )
            return
        
        try:
            user_chat_id = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Неверный формат chat_id")
            return
        
        if subscribers_manager.unblock_subscriber(user_chat_id):
            await update.message.reply_text(f"✅ Пользователь {user_chat_id} разблокирован (сигналы снова приходят)")
        else:
            await update.message.reply_text(f"⚠️ Пользователь {user_chat_id} не найден")
    
    async def users_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /users - показывает список всех подписчиков (только для админа)"""
        chat_id = update.message.chat_id
        
        if str(chat_id) != str(self.chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        subscribers = subscribers_manager.get_subscribers()
        
        if not subscribers:
            await update.message.reply_text("📊 Нет подписанных пользователей.")
            return
        
        message = "📊 <b>Список подписчиков</b>\n\n"
        
        for chat_id_str, data in subscribers.items():
            username = data.get('username', 'unknown')
            first_name = data.get('first_name', 'unknown')
            subscribed_at = data.get('subscribed_at', 'unknown')[:16]
            is_blocked = data.get('is_blocked', False)
            
            status = "🔴 ЗАБЛОКИРОВАН" if is_blocked else "🟢 АКТИВЕН"
            
            message += f"👤 @{username} ({first_name})\n"
            message += f"   🆔 {chat_id_str}\n"
            message += f"   📅 {subscribed_at}\n"
            message += f"   📊 {status}\n\n"
        
        message += f"\n📊 Всего: {len(subscribers)} пользователей"
        
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Команда /broadcast - отправляет сообщение всем подписанным пользователям (только для админа)"""
        chat_id = update.message.chat_id
        
        if str(chat_id) != str(self.chat_id):
            await update.message.reply_text("⛔ Доступ запрещён.")
            return
        
        args = context.args
        if not args:
            await update.message.reply_text(
                "📝 Использование: /broadcast <текст сообщения>\n"
                "Пример: /broadcast Всем привет! Бот обновлён."
            )
            return
        
        message_text = ' '.join(args)
        
        subscribers = subscribers_manager.get_all_subscribers_list()
        
        if not subscribers:
            await update.message.reply_text("⚠️ Нет подписанных пользователей для рассылки.")
            return
        
        await update.message.reply_text(
            f"📨 <b>Начинаю рассылку</b>\n\n"
            f"👥 Получателей: {len(subscribers)}\n"
            f"📝 Сообщение: {message_text}\n\n"
            f"⏳ Идёт отправка...",
            parse_mode='HTML'
        )
        
        success_count = 0
        fail_count = 0
        
        for user_chat_id in subscribers:
            try:
                await self.bot.send_message(
                    chat_id=user_chat_id,
                    text=f"📢 <b>Сообщение от администратора</b>\n\n{message_text}",
                    parse_mode='HTML'
                )
                success_count += 1
                await asyncio.sleep(0.3)
            except Exception as e:
                fail_count += 1
                logger.error(f"❌ Ошибка отправки пользователю {user_chat_id}: {e}")
        
        await update.message.reply_text(
            f"✅ <b>Рассылка завершена!</b>\n\n"
            f"📨 Успешно доставлено: {success_count}\n"
            f"❌ Не доставлено: {fail_count}\n"
            f"👥 Всего получателей: {len(subscribers)}",
            parse_mode='HTML'
        )
        
        logger.info(f"📨 Рассылка завершена: {success_count} успешно, {fail_count} ошибок")
    
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