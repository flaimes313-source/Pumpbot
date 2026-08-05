import asyncio
import websockets
import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class TradeStream:
    """Поток публичных трейдов Bybit для подсчёта количества сделок"""
    
    def __init__(self):
        self.trades = defaultdict(lambda: deque(maxlen=1000))  # Храним последние 1000 трейдов
        self.trade_counts = defaultdict(int)
        self.last_reset = datetime.now()
        self.ws = None
        self.running = False
        self.symbols = []
        
    async def connect(self, symbols):
        """Подключение к WebSocket Bybit"""
        self.symbols = symbols
        self.running = True
        
        # Формируем подписку на все символы
        # Bybit WebSocket: публичный поток для линейных контрактов
        subscribe_topics = []
        for symbol in symbols:
            subscribe_topics.append(f"publicBT.{symbol}.trades")
        
        subscribe_msg = {
            "op": "subscribe",
            "args": subscribe_topics
        }
        
        try:
            # Подключаемся к публичному WebSocket Bybit
            async with websockets.connect("wss://stream.bybit.com/v5/public/linear") as ws:
                self.ws = ws
                await ws.send(json.dumps(subscribe_msg))
                logger.info(f"✅ Подключен к WebSocket Bybit, подписан на {len(symbols)} символов")
                
                while self.running:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=30)
                        await self._process_message(message)
                    except asyncio.TimeoutError:
                        # Пинг для поддержания соединения
                        await ws.send(json.dumps({"op": "ping"}))
                    except Exception as e:
                        logger.error(f"Ошибка WebSocket: {e}")
                        break
                        
        except Exception as e:
            logger.error(f"❌ Ошибка подключения WebSocket: {e}")
            
    async def _process_message(self, message):
        """Обработка входящего сообщения"""
        try:
            data = json.loads(message)
            
            # Проверяем пинг-понг
            if data.get('op') == 'pong':
                return
            
            # Проверяем данные трейдов
            if 'topic' in data and 'data' in data:
                topic = data['topic']
                # Извлекаем символ из топика: publicBT.SYMBOL.trades
                parts = topic.split('.')
                if len(parts) >= 3:
                    symbol = parts[1]
                    trades = data['data']
                    
                    # Подсчитываем количество сделок
                    if trades:
                        self.trades[symbol].extend(trades)
                        self.trade_counts[symbol] += len(trades)
                        
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
    
    def get_trade_count(self, symbol, minutes=5):
        """Получает количество сделок за последние N минут"""
        if symbol not in self.trades:
            return 0
        
        # Очищаем старые трейды
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        valid_trades = []
        for trade in self.trades[symbol]:
            # По умолчанию считаем все трейды за последние N минут
            # В реальности нужно парсить timestamp из трейда
            valid_trades.append(trade)
        
        # Если список слишком большой - обрезаем
        if len(valid_trades) > 1000:
            valid_trades = valid_trades[-1000:]
            self.trades[symbol] = deque(valid_trades, maxlen=1000)
        
        return len(valid_trades)
    
    def get_trade_count_growth(self, symbol):
        """Получает рост количества сделок за 5 минут vs среднее за 30 минут"""
        recent = self.get_trade_count(symbol, 5)
        avg = self.get_trade_count(symbol, 30) / 6 if self.get_trade_count(symbol, 30) > 0 else 0
        
        if avg > 0:
            return recent / avg
        return 1.0
    
    def stop(self):
        """Остановка WebSocket"""
        self.running = False
        if self.ws:
            asyncio.create_task(self.ws.close())
        logger.info("WebSocket остановлен")

# Глобальный экземпляр
trade_stream = TradeStream()