# 🚀 Bybit Pump Detector Bot

Бот для обнаружения пампов на Bybit в реальном времени.

## 📋 Особенности

- ✅ Мониторинг 8+ мем-монет (DOGE, SHIB, PEPE, BONK, WIF, FLOKI, MEME, BABYDOGE)
- ✅ Анализ объёма, OI, Funding, ликвидаций
- ✅ Фильтры: ATR, уровни сопротивления, спот/фьючерс
- ✅ Оповещения в Telegram
- ✅ История OI в памяти

## 🛠️ Установка

```bash
# Клонируем репозиторий
git clone https://github.com/yourusername/bybit-pump-bot.git
cd bybit-pump-bot

# Создаём виртуальное окружение
python -m venv venv

# Активируем (Windows)
venv\Scripts\activate
# Или (Mac/Linux)
source venv/bin/activate

# Устанавливаем зависимости
pip install -r requirements.txt

# Копируем .env.example в .env и заполняем
cp .env.example .env