from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from config import config
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Отправка уведомлений в Telegram"""
    
    def __init__(self):
        self.bot = Bot(token=config.TELEGRAM_TOKEN)
        self.chat_id = config.TELEGRAM_CHAT_ID
        self.application = None
        logger.info("Telegram бот инициализирован")
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработчик команды /start
        Отправляет приветственное сообщение с информацией о боте
        """
        user = update.effective_user
        user_name = user.first_name if user.first_name else "Пользователь"
        
        message = f"""
👋 <b>Привет, {user_name}!</b>

🚀 <b>BYBIT PUMP DETECTOR v2.0</b>

Я бот, который сканирует <b>Bybit</b> в реальном времени 
и ищет потенциальные пампы на основе анализа:

📊 <b>Что я проверяю:</b>
• 📈 Всплеск объёма (+30 баллов)
• 💰 Рост Open Interest (+20 баллов)
• ⚡ Изменение Funding (+15 баллов)
• 📊 Рост цены (+15 баллов)

━━━━━━━━━━━━━━━━━━━━━
🎯 <b>Текущие настройки:</b>
• Максимум монет: {config.MAX_SYMBOLS}
• Топ сигналов: {config.TOP_SIGNALS}
• Порог срабатывания: {config.SCORE_THRESHOLD}/100
• Интервал сканирования: {config.CHECK_INTERVAL} сек
• Минимальный объём: ${config.MIN_VOLUME_USD:,.0f}
━━━━━━━━━━━━━━━━━━━━━

📱 <b>Как это работает:</b>
1️⃣ Каждые {config.CHECK_INTERVAL} секунд сканирую рынок
2️⃣ Если нахожу памп → присылаю <b>СО ЗВУКОМ</b> 🔔
3️⃣ Если сигналов нет → присылаю <b>БЕЗ ЗВУКА</b> 📊

ℹ️ <b>Статистика за сегодня:</b>
• Всего проверено монет: <i>загружаю...</i>
• Найдено сигналов: <i>загружаю...</i>

──────────────
⚙️ <b>Команды:</b>
/start - Показать это сообщение
/status - Статус сканирования
/help - Помощь

⚠️ <i>Торговля криптовалютами связана с высоким риском.
Все решения принимайте на свой страх и риск.</i>
"""
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработчик команды /status
        Показывает текущий статус бота
        """
        message = f"""
📊 <b>Статус бота</b>
🕐 {datetime.now().strftime('%H:%M:%S')}

📈 <b>Настройки:</b>
• Интервал: {config.CHECK_INTERVAL} сек
• Порог: {config.SCORE_THRESHOLD}/100
• Максимум монет: {config.MAX_SYMBOLS}

✅ <b>Статус:</b> Работает
🔄 <b>Последнее сканирование:</b> {datetime.now().strftime('%H:%M:%S')}

💡 <b>Совет:</b> 
Для получения сигналов просто ждите.
Бот сам пришлёт уведомление при обнаружении пампа!
"""
        await update.message.reply_text(message, parse_mode='HTML')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработчик команды /help
        Показывает справку по боту
        """
        message = """
❓ <b>Помощь</b>

📌 <b>Что делает бот?</b>
Сканирует Bybit и ищет потенциальные пампы.

📌 <b>Как работают сигналы?</b>
Каждые 5 минут бот проверяет монеты.
Если находит памп - присылает <b>СО ЗВУКОМ</b> 🔔

📌 <b>Что значат баллы?</b>
• 80-100: 🔴 ВЫСОКАЯ вероятность
• 70-79: 🟡 СРЕДНЯЯ вероятность
• 60-69: 🟢 НИЗКАЯ вероятность

📌 <b>Как я считаю?</b>
• Всплеск объёма → до 30 баллов
• Рост OI → до 20 баллов
• Funding → до 15 баллов
• Рост цены → до 15 баллов

📌 <b>Где взять токен?</b>
Получите у @BotFather

📌 <b>Где взять Chat ID?</b>
Напишите @userinfobot

──────────────
⚙️ <b>Команды:</b>
/start - Приветствие
/status - Статус бота
/help - Эта справка

⚠️ <i>Все решения по торговле - на ваш страх и риск.</i>
"""
        await update.message.reply_text(message, parse_mode='HTML')
    
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
        
        # Сначала статус без звука
        await self.send_scan_status(len(signals))
        
        # Заголовок со звуком
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
    
    async def start_bot(self):
        """Запуск Telegram бота для обработки команд"""
        try:
            # Создаём приложение
            self.application = Application.builder().token(config.TELEGRAM_TOKEN).build()
            
            # Регистрируем команды
            self.application.add_handler(CommandHandler("start", self.start_command))
            self.application.add_handler(CommandHandler("status", self.status_command))
            self.application.add_handler(CommandHandler("help", self.help_command))
            
            # Запускаем polling
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling()
            
            logger.info("✅ Telegram бот запущен, команды /start, /status, /help доступны")
            return True
        except Exception as e:
            logger.error(f"Ошибка запуска Telegram бота: {e}")
            return False
    
    async def stop_bot(self):
        """Остановка Telegram бота"""
        try:
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Telegram бот остановлен")
        except Exception as e:
            logger.error(f"Ошибка остановки Telegram бота: {e}")
