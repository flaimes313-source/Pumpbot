from telegram import Bot
from config import config
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class TelegramNotifier:
    """Отправка уведомлений в Telegram"""
    
    def __init__(self):
        self.bot = Bot(token=config.TELEGRAM_TOKEN)
        self.chat_id = config.TELEGRAM_CHAT_ID
        logger.info("Telegram бот инициализирован")
    
    async def send_message(self, text, silent=False):
        """
        Отправка сообщения
        silent=True - без звука (тихое уведомление)
        silent=False - со звуком
        """
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True,
                disable_notification=silent  # True = без звука, False = со звуком
            )
            logger.info(f"Сообщение отправлено в Telegram (silent={silent})")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
            return False
    
    async def send_scan_status(self, signals_count):
        """
        Отправка статуса сканирования
        Всегда без звука (silent=True)
        """
        message = f"""
📊 <b>Сканирование завершено</b>
🕐 {datetime.now().strftime('%H:%M:%S')}

📈 Найдено сигналов: <b>{signals_count}</b>
{'🔍 Продолжаем мониторинг...' if signals_count == 0 else '🚀 Есть потенциальные пампы!'}
"""
        # Отправляем БЕЗ звука (silent=True)
        return await self.send_message(message, silent=True)
    
    async def send_top_signals(self, signals):
        """
        Отправка топ сигналов
        СО ЗВУКОМ! (silent=False)
        """
        if not signals:
            # Если сигналов нет - отправляем статус без звука
            return await self.send_scan_status(0)
        
        # ============================================
        # ЕСЛИ СИГНАЛЫ ЕСТЬ - ОТПРАВЛЯЕМ С ЗВУКОМ!
        # ============================================
        
        # Сначала отправляем статус без звука
        await self.send_scan_status(len(signals))
        
        # Заголовок с эмодзи (со звуком)
        message = f"""
🔔🔊 <b>ВНИМАНИЕ! ОБНАРУЖЕНЫ ПАМП-СИГНАЛЫ!</b>

🚀 <b>ТОП-{min(len(signals), config.TOP_SIGNALS)} ПАМП СИГНАЛОВ</b>
📅 {datetime.now().strftime('%H:%M:%S')}
📊 Всего найдено: {len(signals)}

"""
        
        # Каждый сигнал
        for i, signal in enumerate(signals[:config.TOP_SIGNALS], 1):
            # Определяем вероятность
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
        
        # Отправляем СО ЗВУКОМ (silent=False)
        return await self.send_message(message, silent=False)
