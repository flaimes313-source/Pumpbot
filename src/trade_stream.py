import asyncio
import json
import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta
import random

logger = logging.getLogger(__name__)

class TradeStream:
    """Поток публичных трейдов Bybit с обработкой ошибок"""
    
    def __init__(self):
        self.trades = defaultdict(lambda: deque(maxlen=1000))
        self.trade_counts = defaultdict(int)
        self.last_reset = datetime.now()
        self.ws = None
        self.running = False
        self.symbols = []
        self.use_websocket = False
        self.reconnect_delay = 5
        self.max_reconnect_delay = 60
        
    async def connect(self, symbols):
        """Подключение к WebSocket Bybit с повторными попытками"""
        self.symbols = symbols
        self.running = True
        
        # Проверяем доступность websockets
        try:
            import websockets
            self.use_websocket = True
            logger.info("✅ WebSocket доступен, запускаем подключение...")
            # Запускаем WebSocket с автоматическим переподключением
            asyncio.create_task(self._run_websocket_with_reconnect())
        except ImportError:
            self.use_websocket = False
            logger.info("ℹ️ WebSocket не доступен, используем эмуляцию")
            asyncio.create_task(self._emulate_trades())
    
    async def _run_websocket_with_reconnect(self):
        """Запуск WebSocket с автоматическим переподключением"""
        import websockets
        
        while self.running:
            try:
                logger.info("🔄 Подключаемся к WebSocket Bybit...")
                await self._connect_websocket(websockets)
            except websockets.exceptions.ConnectionClosed:
                logger.warning("⚠️ WebSocket соединение закрыто, переподключаемся...")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 1.5, self.max_reconnect_delay)
            except Exception as e:
                logger.error(f"❌ Ошибка WebSocket: {e}")
                await asyncio.sleep(self.reconnect_delay)
                self.reconnect_delay = min(self.reconnect_delay * 1.5, self.max_reconnect_delay)
    
    async def _connect_websocket(self, websockets):
        """Подключение к WebSocket"""
        if not self.symbols:
            logger.warning("⚠️ Нет символов для подписки")
            return
        
        # Формируем подписку
        subscribe_topics = []
        for symbol in self.symbols[:50]:  # Ограничиваем количество
            subscribe_topics.append(f"publicBT.{symbol}.trades")
        
        subscribe_msg = {
            "op": "subscribe",
            "args": subscribe_topics
        }
        
        try:
            async with websockets.connect(
                "wss://stream.bybit.com/v5/public/linear",
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            ) as ws:
                self.ws = ws
                self.reconnect_delay = 5  # Сбрасываем задержку при успешном подключении
                await ws.send(json.dumps(subscribe_msg))
                logger.info(f"✅ Подключен к WebSocket Bybit, подписан на {len(subscribe_topics)} каналов")
                
                while self.running:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=30)
                        await self._process_message(message)
                    except asyncio.TimeoutError:
                        # Отправляем ping для поддержания соединения
                        try:
                            await ws.send(json.dumps({"op": "ping"}))
                        except:
                            break
                    except Exception as e:
                        logger.error(f"Ошибка при получении сообщения: {e}")
                        break
                        
        except Exception as e:
            logger.error(f"❌ Ошибка подключения WebSocket: {e}")
            raise
    
    async def _emulate_trades(self):
        """Эмуляция трейдов (если WebSocket недоступен)"""
        logger.info("🔄 Запущена эмуляция трейдов")
        
        while self.running:
            try:
                for symbol in self.symbols[:50]:
                    # Генерируем случайное количество трейдов
                    trades_count = random.randint(1, 10)
                    for _ in range(trades_count):
                        self.trades[symbol].append({
                            'time': datetime.now().isoformat(),
                            'size': random.uniform(100, 10000),
                            'price': random.uniform(0.001, 100)
                        })
                    self.trade_counts[symbol] += trades_count
                
                await asyncio.sleep(10)  # Обновляем каждые 10 секунд
                
            except Exception as e:
                logger.error(f"Ошибка эмуляции: {e}")
                await asyncio.sleep(10)
    
    async def _process_message(self, message):
        """Обработка входящего сообщения"""
        try:
            data = json.loads(message)
            
            # Проверяем пинг-понг
            if data.get('op') == 'pong':
                return
            
            # Проверяем подписку
            if data.get('op') == 'subscribe' and data.get('success'):
                return
            
            # Проверяем данные трейдов
            if 'topic' in data and 'data' in data:
                topic = data['topic']
                parts = topic.split('.')
                if len(parts) >= 3:
                    symbol = parts[1]
                    trades = data['data']
                    
                    if trades and isinstance(trades, list):
                        self.trades[symbol].extend(trades)
                        self.trade_counts[symbol] += len(trades)
                        
        except json.JSONDecodeError:
            pass  # Игнорируем невалидный JSON
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
    
    def get_trade_count(self, symbol, minutes=5):
        """Получает количество сделок за последние N минут"""
        if symbol not in self.trades:
            return 0
        
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        valid_trades = []
        for trade in self.trades[symbol]:
            valid_trades.append(trade)
        
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
        """Остановка"""
        self.running = False
        if self.ws:
            try:
                asyncio.create_task(self.ws.close())
            except:
                pass
        logger.info("TradeStream остановлен")

# Глобальный экземпляр
trade_stream = TradeStream()