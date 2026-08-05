from pybit.unified_trading import HTTP
from config import config
import pandas as pd
import logging
import time
import random
from requests.exceptions import ConnectionError, Timeout

logger = logging.getLogger(__name__)

class BybitClient:
    """Клиент для работы с Bybit API (только публичные данные)"""
    
    def __init__(self):
        self.session = HTTP(
            testnet=False,
            api_key=None,
            api_secret=None
        )
        self.all_symbols = []
        self.spot_symbols = []
        self.linear_symbols = []
        logger.info("Bybit клиент инициализирован")
    
    def _make_request(self, func, *args, **kwargs):
        """
        Выполняет запрос с повторными попытками в случае ошибки
        """
        max_retries = 5
        retry_delay = 3
        
        for attempt in range(max_retries):
            try:
                response = func(*args, **kwargs)
                return response
            except (ConnectionError, Timeout) as e:
                logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries} не удалась: {e}")
                if attempt < max_retries - 1:
                    # Экспоненциальная задержка с джиттером
                    delay = retry_delay * (1.5 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
                else:
                    logger.error(f"❌ Все попытки ({max_retries}) не удались")
                    raise
            except Exception as e:
                logger.error(f"❌ Неизвестная ошибка: {e}")
                raise
        
        return None
    
    def load_all_symbols(self):
        """Загружает все USDT пары с Bybit с повторными попытками"""
        logger.info("Загрузка всех торговых пар с Bybit...")
        
        try:
            # 1. Загружаем спотовые пары
            spot_resp = self._make_request(
                self.session.get_instruments_info,
                category="spot",
                limit=1000
            )
            if spot_resp and spot_resp['retCode'] == 0:
                self.spot_symbols = [
                    item['symbol'] 
                    for item in spot_resp['result']['list'] 
                    if item['status'] == 'Trading' and 'USDT' in item['symbol']
                ]
                logger.info(f"✅ Загружено {len(self.spot_symbols)} спотовых пар USDT")
            else:
                logger.error(f"❌ Ошибка загрузки спотовых пар: {spot_resp}")
                return self._get_fallback_symbols()
            
            # 2. Загружаем фьючерсные пары (Linear)
            linear_resp = self._make_request(
                self.session.get_instruments_info,
                category="linear",
                limit=1000
            )
            if linear_resp and linear_resp['retCode'] == 0:
                self.linear_symbols = [
                    item['symbol'] 
                    for item in linear_resp['result']['list'] 
                    if item['status'] == 'Trading' and 'USDT' in item['symbol']
                ]
                logger.info(f"✅ Загружено {len(self.linear_symbols)} фьючерсных пар USDT")
            else:
                logger.error(f"❌ Ошибка загрузки фьючерсных пар: {linear_resp}")
                return self._get_fallback_symbols()
            
            # 3. Пересечение
            spot_set = set(self.spot_symbols)
            linear_set = set(self.linear_symbols)
            self.all_symbols = list(spot_set.intersection(linear_set))
            
            if not self.all_symbols:
                logger.warning("⚠️ Не найдено общих пар между спотом и фьючерсами")
                return self._get_fallback_symbols()
            
            # Сортируем по объёму
            self.all_symbols = self._sort_by_volume(self.all_symbols)
            
            logger.info(f"✅ Найдено {len(self.all_symbols)} монет для анализа")
            return self.all_symbols
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки инструментов: {e}")
            return self._get_fallback_symbols()
    
    def _get_fallback_symbols(self):
        """Возвращает резервный список популярных монет"""
        fallback = ['DOGEUSDT', 'SHIBUSDT', 'PEPEUSDT', 'WIFUSDT', 'MEMEUSDT', 'BONKUSDT']
        logger.info(f"🔧 Используем резервный список: {fallback}")
        return fallback
    
    def _sort_by_volume(self, symbols):
        """Сортировка по 24h объёму с повторными попытками"""
        volumes = {}
        for symbol in symbols[:100]:
            try:
                ticker = self._make_request(
                    self.session.get_tickers,
                    category="linear",
                    symbol=symbol
                )
                if ticker and ticker['retCode'] == 0 and ticker['result']['list']:
                    volume = float(ticker['result']['list'][0]['turnover24h'])
                    volumes[symbol] = volume
                time.sleep(0.1)  # Небольшая задержка между запросами
            except:
                pass
        return sorted(volumes.keys(), key=lambda x: volumes.get(x, 0), reverse=True)
    
    def get_klines(self, symbol, interval='5', limit=100):
        """Получение свечей с повторными попытками"""
        try:
            response = self._make_request(
                self.session.get_kline,
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            if response and response['retCode'] == 0:
                data = response['result']['list']
                
                if not data:
                    logger.warning(f"⚠️ Нет данных для {symbol}")
                    return pd.DataFrame()
                
                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])
                
                # --- ИСПРАВЛЕНИЕ ОШИБКИ Python int too large to convert to C long ---
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                # --------------------------------------------------------------------

                df['close'] = df['close'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['volume'] = df['volume'].astype(float)
                
                return df
        except Exception as e:
            logger.error(f"❌ Ошибка получения свечей {symbol}: {e}")
        return pd.DataFrame()
    
    def get_funding_rate(self, symbol):
        """Текущий funding rate"""
        try:
            response = self._make_request(
                self.session.get_tickers,
                category="linear",
                symbol=symbol
            )
            if response and response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['fundingRate'])
        except Exception as e:
            logger.error(f"❌ Ошибка получения funding {symbol}: {e}")
        return 0.0
    
    def get_open_interest(self, symbol):
        """Текущий Open Interest"""
        try:
            response = self._make_request(
                self.session.get_open_interest,
                category="linear",
                symbol=symbol,
                intervalTime="5min"
            )
            if response and response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['openInterest'])
        except Exception as e:
            logger.error(f"❌ Ошибка получения OI {symbol}: {e}")
        return 0.0
    
    def get_current_price(self, symbol):
        """Текущая цена"""
        try:
            response = self._make_request(
                self.session.get_tickers,
                category="linear",
                symbol=symbol
            )
            if response and response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['lastPrice'])
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены {symbol}: {e}")
        return 0.0
    
    def get_24h_volume_usd(self, symbol):
        """24h объём фьючерсов в USD"""
        try:
            response = self._make_request(
                self.session.get_tickers,
                category="linear",
                symbol=symbol
            )
            if response and response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['turnover24h'])
        except Exception as e:
            logger.error(f"❌ Ошибка получения 24h объёма USD {symbol}: {e}")
        return 0.0