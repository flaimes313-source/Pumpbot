import requests
import pandas as pd
import logging
import time
import random
from config import config

logger = logging.getLogger(__name__)

class BybitClient:
    """Клиент для работы с Bybit API (использует requests вместо pybit)"""
    
    BASE_URL = "https://api.bybit.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.all_symbols = []
        self.spot_symbols = []
        self.linear_symbols = []
        logger.info("Bybit клиент инициализирован (requests)")
    
    def _make_request(self, endpoint, params=None, max_retries=5):
        """
        Выполняет запрос к API с повторными попытками
        """
        retry_delay = 3
        
        for attempt in range(max_retries):
            try:
                url = f"{self.BASE_URL}{endpoint}"
                response = self.session.get(url, params=params, timeout=15)
                response.raise_for_status()
                data = response.json()
                
                if data.get('retCode') == 0:
                    return data
                else:
                    logger.error(f"API ошибка: {data.get('retMsg')}")
                    return None
                    
            except requests.exceptions.ConnectionError as e:
                logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries} - ConnectionError: {e}")
                if attempt < max_retries - 1:
                    delay = retry_delay * (1.5 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
                else:
                    logger.error(f"❌ Все попытки ({max_retries}) не удались")
                    raise
                    
            except requests.exceptions.Timeout as e:
                logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries} - Timeout: {e}")
                if attempt < max_retries - 1:
                    delay = retry_delay * (1.5 ** attempt) + random.uniform(0, 1)
                    time.sleep(delay)
                else:
                    logger.error(f"❌ Все попытки ({max_retries}) не удались")
                    raise
                    
            except Exception as e:
                logger.error(f"❌ Неизвестная ошибка: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    raise
        
        return None
    
    def load_all_symbols(self):
        """Загружает все USDT пары с Bybit"""
        logger.info("Загрузка всех торговых пар с Bybit...")
        
        try:
            # 1. Загружаем спотовые пары
            spot_resp = self._make_request(
                "/v5/market/instruments-info",
                {"category": "spot", "limit": 1000}
            )
            if spot_resp:
                self.spot_symbols = [
                    item['symbol'] 
                    for item in spot_resp['result']['list'] 
                    if item['status'] == 'Trading' and 'USDT' in item['symbol']
                ]
                logger.info(f"✅ Загружено {len(self.spot_symbols)} спотовых пар USDT")
            else:
                logger.error("❌ Ошибка загрузки спотовых пар")
                return self._get_fallback_symbols()
            
            # 2. Загружаем фьючерсные пары (Linear)
            linear_resp = self._make_request(
                "/v5/market/instruments-info",
                {"category": "linear", "limit": 1000}
            )
            if linear_resp:
                self.linear_symbols = [
                    item['symbol'] 
                    for item in linear_resp['result']['list'] 
                    if item['status'] == 'Trading' and 'USDT' in item['symbol']
                ]
                logger.info(f"✅ Загружено {len(self.linear_symbols)} фьючерсных пар USDT")
            else:
                logger.error("❌ Ошибка загрузки фьючерсных пар")
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
        """Сортировка по 24h объёму"""
        volumes = {}
        for symbol in symbols[:100]:
            try:
                data = self._make_request(
                    "/v5/market/tickers",
                    {"category": "linear", "symbol": symbol},
                    max_retries=3
                )
                if data and data['result']['list']:
                    volume = float(data['result']['list'][0]['turnover24h'])
                    volumes[symbol] = volume
                time.sleep(0.1)
            except:
                pass
        return sorted(volumes.keys(), key=lambda x: volumes.get(x, 0), reverse=True)
    
    def get_klines(self, symbol, interval='5', limit=100):
        """Получение свечей"""
        try:
            data = self._make_request(
                "/v5/market/kline",
                {
                    "category": "linear",
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit
                }
            )
            
            if data and data['result']['list']:
                rows = data['result']['list']
                df = pd.DataFrame(rows, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])
                df['close'] = df['close'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['volume'] = df['volume'].astype(float)
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='ms')
                return df
            else:
                logger.warning(f"⚠️ Нет данных для {symbol}")
                return pd.DataFrame()
                
        except Exception as e:
            logger.error(f"❌ Ошибка получения свечей {symbol}: {e}")
        return pd.DataFrame()
    
    def get_funding_rate(self, symbol):
        """Текущий funding rate"""
        try:
            data = self._make_request(
                "/v5/market/tickers",
                {"category": "linear", "symbol": symbol}
            )
            if data and data['result']['list']:
                return float(data['result']['list'][0]['fundingRate'])
        except Exception as e:
            logger.error(f"❌ Ошибка получения funding {symbol}: {e}")
        return 0.0
    
    def get_open_interest(self, symbol):
        """Текущий Open Interest"""
        try:
            data = self._make_request(
                "/v5/market/open-interest",
                {
                    "category": "linear",
                    "symbol": symbol,
                    "intervalTime": "5min"
                }
            )
            if data and data['result']['list']:
                return float(data['result']['list'][0]['openInterest'])
        except Exception as e:
            logger.error(f"❌ Ошибка получения OI {symbol}: {e}")
        return 0.0
    
    def get_current_price(self, symbol):
        """Текущая цена"""
        try:
            data = self._make_request(
                "/v5/market/tickers",
                {"category": "linear", "symbol": symbol}
            )
            if data and data['result']['list']:
                return float(data['result']['list'][0]['lastPrice'])
        except Exception as e:
            logger.error(f"❌ Ошибка получения цены {symbol}: {e}")
        return 0.0
    
    def get_24h_volume_usd(self, symbol):
        """24h объём фьючерсов в USD"""
        try:
            data = self._make_request(
                "/v5/market/tickers",
                {"category": "linear", "symbol": symbol}
            )
            if data and data['result']['list']:
                return float(data['result']['list'][0]['turnover24h'])
        except Exception as e:
            logger.error(f"❌ Ошибка получения 24h объёма USD {symbol}: {e}")
        return 0.0