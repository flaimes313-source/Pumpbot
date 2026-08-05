from pybit.unified_trading import HTTP
from config import config
import pandas as pd
import logging

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
    
    def load_all_symbols(self):
        """Загружает все USDT пары с Bybit"""
        logger.info("Загрузка всех торговых пар с Bybit...")
        
        try:
            # 1. Спотовые пары
            spot_resp = self.session.get_instruments_info(
                category="spot",
                limit=1000
            )
            if spot_resp['retCode'] == 0:
                self.spot_symbols = [
                    item['symbol'] 
                    for item in spot_resp['result']['list'] 
                    if item['status'] == 'Trading' and 'USDT' in item['symbol']
                ]
                logger.info(f"✅ Загружено {len(self.spot_symbols)} спотовых пар USDT")
            
            # 2. Фьючерсные пары (Linear)
            linear_resp = self.session.get_instruments_info(
                category="linear",
                limit=1000
            )
            if linear_resp['retCode'] == 0:
                self.linear_symbols = [
                    item['symbol'] 
                    for item in linear_resp['result']['list'] 
                    if item['status'] == 'Trading' and 'USDT' in item['symbol']
                ]
                logger.info(f"✅ Загружено {len(self.linear_symbols)} фьючерсных пар USDT")
            
            # 3. Пересечение
            spot_set = set(self.spot_symbols)
            linear_set = set(self.linear_symbols)
            self.all_symbols = list(spot_set.intersection(linear_set))
            
            self.all_symbols = self._sort_by_volume(self.all_symbols)
            
            logger.info(f"✅ Найдено {len(self.all_symbols)} монет для анализа")
            return self.all_symbols
            
        except Exception as e:
            logger.error(f"Ошибка загрузки инструментов: {e}")
            return []
    
    def _sort_by_volume(self, symbols):
        """Сортировка по 24h объёму"""
        volumes = {}
        for symbol in symbols[:100]:
            try:
                ticker = self.session.get_tickers(
                    category="linear",
                    symbol=symbol
                )
                if ticker['retCode'] == 0 and ticker['result']['list']:
                    volume = float(ticker['result']['list'][0]['turnover24h'])
                    volumes[symbol] = volume
            except:
                pass
        return sorted(volumes.keys(), key=lambda x: volumes.get(x, 0), reverse=True)
    
    def get_klines(self, symbol, interval='5', limit=100):
        """Получение свечей"""
        try:
            response = self.session.get_kline(
                category="linear",
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            if response['retCode'] == 0:
                data = response['result']['list']
                
                # Добавим проверку, чтобы не ломаться, если пришел пустой список
                if not data:
                    return pd.DataFrame()

                df = pd.DataFrame(data, columns=[
                    'timestamp', 'open', 'high', 'low', 'close', 'volume', 'turnover'
                ])
                
                # --- ИСПРАВЛЕНИЕ ОШИБКИ Python int too large to convert to C long ---
                # Безопасно конвертируем строку timestamp в число, а затем в дату
                df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                # --------------------------------------------------------------------

                df['close'] = df['close'].astype(float)
                df['high'] = df['high'].astype(float)
                df['low'] = df['low'].astype(float)
                df['volume'] = df['volume'].astype(float)
                
                return df
        except Exception as e:
            logger.error(f"Ошибка получения свечей {symbol}: {e}")
        return pd.DataFrame()
    
    def get_funding_rate(self, symbol):
        """Текущий funding rate"""
        try:
            response = self.session.get_tickers(
                category="linear",
                symbol=symbol
            )
            if response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['fundingRate'])
        except Exception as e:
            logger.error(f"Ошибка получения funding {symbol}: {e}")
        return 0.0
    
    def get_open_interest(self, symbol):
        """Текущий Open Interest"""
        try:
            response = self.session.get_open_interest(
                category="linear",
                symbol=symbol,
                intervalTime="5min"
            )
            if response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['openInterest'])
        except Exception as e:
            logger.error(f"Ошибка получения OI {symbol}: {e}")
        return 0.0
    
    def get_current_price(self, symbol):
        """Текущая цена"""
        try:
            response = self.session.get_tickers(
                category="linear",
                symbol=symbol
            )
            if response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['lastPrice'])
        except Exception as e:
            logger.error(f"Ошибка получения цены {symbol}: {e}")
        return 0.0
    
    def get_24h_volume_usd(self, symbol):
        """24h объём фьючерсов в USD"""
        try:
            response = self.session.get_tickers(
                category="linear",
                symbol=symbol
            )
            if response['retCode'] == 0 and response['result']['list']:
                return float(response['result']['list'][0]['turnover24h'])
        except Exception as e:
            logger.error(f"Ошибка получения 24h объёма USD {symbol}: {e}")
        return 0.0