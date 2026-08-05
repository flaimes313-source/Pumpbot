from collections import deque
from datetime import datetime, timedelta
from config import config
from src.bybit_client import BybitClient
from src.indicators import Indicators
import logging

logger = logging.getLogger(__name__)

class PumpDetector:
    """Детектор пампов - сканирует все монеты"""
    
    def __init__(self):
        self.client = BybitClient()
        self.indicators = Indicators()
        self.oi_history = {}
        self.results = []
    
    def scan_all_symbols(self):
        """Сканирует все монеты и возвращает топ по рейтингу"""
        logger.info("="*50)
        logger.info("🚀 Начинаем сканирование всех монет...")
        
        symbols = self.client.load_all_symbols()
        if not symbols:
            logger.error("❌ Не удалось загрузить символы")
            return []
        
        symbols_to_check = symbols[:config.MAX_SYMBOLS]
        logger.info(f"📊 Проверяем {len(symbols_to_check)} монет из {len(symbols)}")
        
        results = []
        failed_count = 0
        
        for i, symbol in enumerate(symbols_to_check, 1):
            try:
                result = self.check_pump(symbol)
                if result and result['score'] >= config.SCORE_THRESHOLD:
                    results.append(result)
                    logger.info(f"✅ [{i}/{len(symbols_to_check)}] {symbol}: {result['score']} баллов")
                else:
                    if i % 10 == 0:
                        logger.info(f"⏳ Проверено {i}/{len(symbols_to_check)} монет...")
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Ошибка при проверке {symbol}: {e}")
        
        results.sort(key=lambda x: x['score'], reverse=True)
        logger.info(f"🏆 Найдено {len(results)} сигналов! (Ошибок: {failed_count})")
        return results[:config.TOP_SIGNALS]
    
    def check_pump(self, symbol):
        """Проверка одной монеты"""
        try:
            # Получаем свечи
            df = self.client.get_klines(symbol, str(config.TIMEFRAME), limit=100)
            if df.empty:
                return None
            
            # Проверяем объём
            volume_usd = self.client.get_24h_volume_usd(symbol)
            if volume_usd < config.MIN_VOLUME_USD:
                return None
            
            current_price = df['close'].iloc[-1]
            score = 0
            details = {}
            
            # 1. Volume
            vol_score, ratio = self.indicators.check_volume_spike(df)
            score += vol_score
            details['Volume'] = f"{ratio:.1f}x (+{vol_score})"
            
            # 2. Price
            if len(df) >= 2:
                price_5m_ago = df['close'].iloc[-2]
                price_change = ((current_price - price_5m_ago) / price_5m_ago) * 100
                
                if price_change > config.PRICE_CHANGE_5M:
                    score += 15
                    details['Price'] = f"+{price_change:.2f}% (+15)"
                else:
                    details['Price'] = f"+{price_change:.2f}% (+0)"
            else:
                details['Price'] = "N/A"
                price_change = 0
            
            # 3. OI
            oi_now, oi_change = self._get_oi_change(symbol)
            if oi_change > config.OI_CHANGE_15M:
                score += 20
                details['OI'] = f"+{oi_change:.1f}% (+20)"
            else:
                details['OI'] = f"+{oi_change:.1f}% (+0)"
            
            # 4. Funding
            funding_now = self.client.get_funding_rate(symbol)
            funding_prev = funding_now - 0.005
            funding_spike = (funding_now - funding_prev) * 100
            
            if funding_spike > config.FUNDING_SPIKE:
                score += 15
                details['Funding'] = f"{funding_now*100:.4f}% (+15)"
            else:
                details['Funding'] = f"{funding_now*100:.4f}% (+0)"
            
            # Фильтры
            atr_24h = self.indicators.calculate_atr(df, period=96)
            atr_4h = self.indicators.calculate_atr(df, period=48)
            
            if atr_24h > config.ATR_MAX_PERCENT_24H:
                return None
            if atr_4h > config.ATR_MAX_PERCENT_4H:
                return None
            
            # Resistance
            resistance, gap = self.indicators.find_resistance_levels(df, current_price)
            if gap < config.RESISTANCE_GAP_MIN:
                return None
            
            if score >= config.SCORE_THRESHOLD:
                return {
                    'symbol': symbol,
                    'score': score,
                    'price': current_price,
                    'price_change': price_change,
                    'volume_ratio': ratio,
                    'oi_change': oi_change,
                    'funding': funding_now,
                    'details': details,
                    'atr_24h': atr_24h,
                    'atr_4h': atr_4h,
                    'resistance_gap': gap,
                    'resistance': resistance
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка в check_pump для {symbol}: {e}")
            return None
    
    def _get_oi_change(self, symbol):
        """Получение изменения OI за 15 минут"""
        try:
            if symbol not in self.oi_history:
                self.oi_history[symbol] = deque(maxlen=10)
            
            current_oi = self.client.get_open_interest(symbol)
            timestamp = datetime.now()
            
            self.oi_history[symbol].append({
                'timestamp': timestamp,
                'oi': current_oi
            })
            
            fifteen_min_ago = timestamp - timedelta(minutes=15)
            oi_15min_ago = None
            
            for record in reversed(self.oi_history[symbol]):
                if record['timestamp'] <= fifteen_min_ago:
                    oi_15min_ago = record['oi']
                    break
            
            if oi_15min_ago and oi_15min_ago > 0:
                oi_change = ((current_oi - oi_15min_ago) / oi_15min_ago) * 100
            else:
                oi_change = 0.0
            
            return current_oi, oi_change
        except Exception as e:
            logger.error(f"❌ Ошибка _get_oi_change для {symbol}: {e}")
            return 0, 0.0