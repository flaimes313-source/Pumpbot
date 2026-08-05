import requests
import pandas as pd
import logging
import time
import random
from config import config

logger = logging.getLogger(__name__)

class BybitClient:
    """Клиент для работы с Bybit API"""
    
    BASE_URL = "https://api.bybit.com"
    
    def __init__(self):
        self.session = requests.Session()
        self.all_symbols = []
        self.spot_symbols = []
        self.linear_symbols = []
        logger.info("Bybit клиент инициализирован")
    
    def _make_request(self, endpoint, params=None, max_retries=3):
        """Выполняет запрос с повторными попытками"""
        retry_delay = 3
        
        for attempt in range(max_retries):
            try:
                url = f"{self.BASE_URL}{endpoint}"
                response = self.session.get(url, params=params, timeout=15)
                
                # Для 404 ошибки не повторяем
                if response.status_code == 404:
                    logger.debug(f"ℹ️ Эндпоинт не найден: {endpoint}")
                    return None
                
                response.raise_for_status()
                data = response.json()
                
                if data.get('retCode') == 0:
                    return data
                else:
                    logger.error(f"API ошибка: {data.get('retMsg')}")
                    return None
                    
            except requests.exceptions.HTTPError as e:
                if response.status_code == 404:
                    return None
                logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    raise
            except Exception as e:
                logger.warning(f"⚠️ Попытка {attempt + 1}/{max_retries}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 1.5
                else:
                    raise
        
        return None
    
    def load_all_symbols(self):
        """Загружает все USDT пары"""
        logger.info("Загрузка торговых пар с Bybit...")
        
        try:
            spot_resp = self._make_request("/v5/market/instruments-info", {"category": "spot", "limit": 1000})
            if spot_resp:
                self.spot_symbols = [
                    item['symbol'] 
                    for item in spot_resp['result']['list'] 
                    if item['status'] == 'Trading' and 'USDT' in item['symbol']
                ]
                logger.info(f"✅ Загружено {len(self.spot_symbols)} спотовых пар")
            
            linear_resp = self._make_request("/v5/market/instruments-info", {"category": "linear", "limit": 1000})
            if linear_resp:
                self.linear_symbols = [
                    item['symbol'] 
                    for item in linear_resp['result']['list'] 
                    if item['status'] == 'Trading' and 'USDT' in item['symbol']
                ]
                logger.info(f"✅ Загружено {len(self.linear_symbols)} фьючерсных пар")
            
            spot_set = set(self.spot_symbols)
            linear_set = set(self.linear_symbols)
            self.all_symbols = list(spot_set.intersection(linear_set))
            
            if not self.all_symbols:
                return self._get_fallback_symbols()
            
            self.all_symbols = self._sort_by_volume(self.all_symbols)
            logger.info(f"✅ Найдено {len(self.all_symbols)} монет")
            return self.all_symbols
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки: {e}")
            return self._get_fallback_symbols()
    
    def _get_fallback_symbols(self):
        fallback = ['DOGEUSDT', 'SHIBUSDT', 'PEPEUSDT', 'WIFUSDT', 'MEMEUSDT']
        logger.info(f"🔧 Резервный список: {fallback}")
        return fallback
    
    def _sort_by_volume(self, symbols):
        volumes = {}
        for symbol in symbols[:100]:
            try:
                data = self._make_request("/v5/market/tickers", {"category": "linear", "symbol": symbol}, max_retries=2)
                if data and data['result']['list']:
                    volume = float(data['result']['list'][0]['turnover24h'])
                    volumes[symbol] = volume
                time.sleep(0.05)
            except:
                pass
        return sorted(volumes.keys(), key=lambda x: volumes.get(x, 0), reverse=True)
    
    def _convert_timestamp(self, timestamp):
        """Безопасное преобразование timestamp"""
        try:
            if isinstance(timestamp, str):
                ts = int(timestamp)
            else:
                ts = int(timestamp)
            
            if ts > 1000000000000:
                ts = ts / 1000
            
            return pd.to_datetime(ts, unit='s')
        except:
            return pd.NaT
    
    def get_klines(self, symbol, interval='5', limit=200):
        """Получение свечей"""
        try:
            data = self._make_request("/v5/market/kline", {
                "category": "linear",
                "symbol": symbol,
                "interval": interval,
                "limit": limit
            })
            
            if data and data['result']['list']:
                rows = data['result']['list']
                df = pd.DataFrame(rows, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])
                df['timestamp'] = df['timestamp'].apply(self._convert_timestamp)
                df['close'] = df['close'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['volume'] = df['volume'].astype(float)
                return df
        except Exception as e:
            logger.error(f"❌ Ошибка получения свечей {symbol}: {e}")
        return pd.DataFrame()
    
    def get_funding_rate(self, symbol):
        """Текущий funding rate через tickers"""
        try:
            data = self._make_request("/v5/market/tickers", {
                "category": "linear",
                "symbol": symbol
            })
            if data and data['result']['list']:
                return float(data['result']['list'][0].get('fundingRate', 0))
        except Exception as e:
            logger.error(f"❌ Ошибка получения funding {symbol}: {e}")
        return 0.0
    
    def get_oi_history(self, symbol, limit=50):
        """История Open Interest"""
        try:
            data = self._make_request("/v5/market/open-interest", {
                "category": "linear",
                "symbol": symbol,
                "intervalTime": "5min",
                "limit": limit
            })
            if data and data['result']['list']:
                df = pd.DataFrame(data['result']['list'])
                df['openInterest'] = df['openInterest'].astype(float)
                df['timestamp'] = df['timestamp'].apply(self._convert_timestamp)
                return df
        except Exception as e:
            logger.error(f"❌ Ошибка получения OI истории {symbol}: {e}")
        return pd.DataFrame()
    
    def get_funding_history(self, symbol, limit=30):
        """История ставок финансирования (если доступно)"""
        try:
            # Пробуем получить историю funding
            data = self._make_request("/v5/market/funding-rate-history", {
                "category": "linear",
                "symbol": symbol,
                "limit": limit
            })
            if data and data['result']['list']:
                df = pd.DataFrame(data['result']['list'])
                df['fundingRate'] = df['fundingRate'].astype(float)
                df['timestamp'] = df['timestamp'].apply(self._convert_timestamp)
                return df
        except Exception as e:
            logger.debug(f"ℹ️ Funding история не доступна для {symbol}")
        return pd.DataFrame()
    
    def get_orderbook(self, symbol, limit=50):
        """Получение стакана заявок"""
        try:
            data = self._make_request("/v5/market/orderbook", {
                "category": "linear",
                "symbol": symbol,
                "limit": limit
            })
            if data and data['result']:
                return {
                    'bids': [[float(x[0]), float(x[1])] for x in data['result']['b'][:20]],
                    'asks': [[float(x[0]), float(x[1])] for x in data['result']['a'][:20]]
                }
        except Exception as e:
            logger.error(f"❌ Ошибка получения стакана {symbol}: {e}")
        return {'bids': [], 'asks': []}
    
    def get_liquidations(self, symbol, limit=100):
        """Получение ликвидаций (если доступно)"""
        try:
            data = self._make_request("/v5/market/liq-records", {
                "category": "linear",
                "symbol": symbol,
                "limit": limit
            })
            if data and data['result']['list']:
                total_long = 0
                total_short = 0
                for liq in data['result']['list']:
                    if liq['side'] == 'Buy':
                        total_long += float(liq['size'])
                    else:
                        total_short += float(liq['size'])
                
                current_price = self.get_current_price(symbol)
                return {
                    'total': (total_long + total_short) * current_price,
                    'long': total_long * current_price,
                    'short': total_short * current_price
                }
        except Exception as e:
            logger.debug(f"ℹ️ Ликвидации не доступны для {symbol}")
        return {'total': 0, 'long': 0, 'short': 0}
    
    def get_current_price(self, symbol):
        try:
            data = self._make_request("/v5/market/tickers", {"category": "linear", "symbol": symbol})
            if data and data['result']['list']:
                return float(data['result']['list'][0]['lastPrice'])
        except:
            pass
        return 0.0
    
    def get_24h_volume_usd(self, symbol):
        try:
            data = self._make_request("/v5/market/tickers", {"category": "linear", "symbol": symbol})
            if data and data['result']['list']:
                return float(data['result']['list'][0]['turnover24h'])
        except:
            pass
        return 0.0