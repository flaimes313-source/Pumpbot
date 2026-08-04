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
    
    async def send_message(self, text):
        """Отправка сообщения"""
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode='HTML',
                disable_web_page_preview=True
            )
            logger.info("Сообщение отправлено в Telegram")
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки в Telegram: {e}")
            return False
    
    async def send_top_signals(self, signals):
        """
        Отправка топ сигналов
        ОТПРАВЛЯЕТ ТОЛЬКО ЕСЛИ ЕСТЬ СИГНАЛЫ!
        """
        # ЕСЛИ СИГНАЛОВ НЕТ - НИЧЕГО НЕ ОТПРАВЛЯЕМ
        if not signals:
            logger.info("ℹ️ Сигналов нет, сообщение не отправлено")
            return True
        
        # ============================================
        # ЕСЛИ СИГНАЛЫ ЕСТЬ - ОТПРАВЛЯЕМ С ЗВУКОМ!
        # ============================================
        
        # Заголовок с эмодзи и звонком
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
        
        # Отправляем сообщение
        result = await self.send_message(message)
        
        # ============================================
        # ОТПРАВЛЯЕМ ЗВУКОВОЕ УВЕДОМЛЕНИЕ!
        # ============================================
        if result:
            await self.send_sound_alert()
        
        return result
    
    async def send_sound_alert(self):
        """
        Отправка звукового уведомления в Telegram
        Использует голосовое сообщение или стикер
        """
        try:
            # Вариант 1: Отправить голосовое сообщение (OGG файл)
            # Для этого нужно загрузить файл на сервер или использовать URL
            # voice_url = "https://example.com/alert.ogg"
            
            # Вариант 2: Отправить аудио (простой способ - использовать уведомление)
            # В Telegram есть встроенный звук для уведомлений @
            
            # Вариант 3: Отправить стикер с звуком (самый простой)
            # Это сработает как обычное сообщение, но с эмодзи и выделением
            
            # Отправляем дополнительное короткое сообщение с @ для звука
            sound_message = """
🔊 <b>‼️ СРАБОТАЛ ДЕТЕКТОР ПАМПОВ ‼️</b>
Проверьте сигналы выше! 🚀
"""
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=sound_message,
                parse_mode='HTML'
            )
            
            # Вариант 4: Отправить голосовое сообщение (если есть файл)
            # with open('alert.ogg', 'rb') as voice:
            #     await self.bot.send_voice(
            #         chat_id=self.chat_id,
            #         voice=voice
            #     )
            
            logger.info("🔊 Звуковое уведомление отправлено")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка отправки звука: {e}")
            return False
