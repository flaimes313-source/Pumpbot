from collections import deque
from datetime import datetime, timedelta
from config import config
from src.bybit_client import BybitClient
from src.indicators import Indicators
import logging

logger = logging.getLogger(__name__)

class PumpDetector:
    """Детектор пампов с расширенными индикаторами"""
    
    def __init__(self):
        self.client = BybitClient()
        self.indicators = Indicators()
        self.oi_history = {}
        self.results = []
    
    def scan_all_symbols(self):
        """Сканирует все монеты"""
        logger.info("="*50)
        logger.info("🚀 Начинаем сканирование...")
        
        symbols = self.client.load_all_symbols()
        if not symbols:
            return []
        
        symbols_to_check = symbols[:config.MAX_SYMBOLS]
        logger.info(f"📊 Проверяем {len(symbols_to_check)} монет")
        
        results = []
        for i, symbol in enumerate(symbols_to_check, 1):
            try:
                result = self.check_pump(symbol)
                if result:
                    results.append(result)
                    logger.info(f"✅ [{i}] {symbol}: {result['score']} баллов")
                elif i % 10 == 0:
                    logger.info(f"⏳ Проверено {i}/{len(symbols_to_check)}")
            except Exception as e:
                logger.error(f"❌ Ошибка {symbol}: {e}")
        
        results.sort(key=lambda x: x['score'], reverse=True)
        logger.info(f"🏆 Найдено {len(results)} сигналов!")
        return results[:config.TOP_SIGNALS]
    
    def check_pump(self, symbol):
        """Проверка одной монеты"""
        try:
            # 1. Свечи
            df = self.client.get_klines(symbol, '5', limit=200)
            if df.empty:
                return None
            
            # 2. OI история
            oi_df = self.client.get_oi_history(symbol, limit=50)
            
            # 3. Funding история
            funding_df = self.client.get_funding_history(symbol, limit=30)
            
            # 4. Стакан
            orderbook = self.client.get_orderbook(symbol)
            
            # 5. Ликвидации
            liq_data = self.client.get_liquidations(symbol)
            
            # 6. Проверка объёма
            volume_usd = self.client.get_24h_volume_usd(symbol)
            if volume_usd < config.MIN_VOLUME_USD:
                return None
            
            current_price = df['close'].iloc[-1]
            score = 0
            details = {}
            
            # ============================================================
            # 1. VOLUME SPIKE (до 30 баллов)
            # ============================================================
            vol_score, vol_ratio = self.indicators.check_volume_spike(df)
            score += vol_score
            details['Volume'] = f"{vol_ratio:.1f}x (+{vol_score})"
            
            # ============================================================
            # 2. OI GROWTH (5/15/30 мин) - до 25 баллов
            # ============================================================
            oi_score, oi_change = self.indicators.check_oi_growth(oi_df)
            score += oi_score
            details['OI'] = f"+{oi_change:.1f}% (+{oi_score})"
            
            # ============================================================
            # 3. CVD (Cumulative Volume Delta) - до 15 баллов
            # ИСПРАВЛЕНО: используем агрессивную сторону (taker)
            # ============================================================
            cvd_score, cvd_delta = self.indicators.calculate_cvd(df)
            score += cvd_score
            details['CVD'] = f"{cvd_delta:.0f} (+{cvd_score})"
            
            # ============================================================
            # 4. BID/ASK IMBALANCE - до 10 баллов
            # ИСПРАВЛЕНО: Top 25 вместо Top 10
            # ============================================================
            bid_score, bid_imbalance = self.indicators.calculate_bid_ask_imbalance(orderbook)
            score += bid_score
            details['Bid/Ask'] = f"{bid_imbalance:.1f}% (+{bid_score})"
            
            # ============================================================
            # 5. PRICE ACCELERATION - до 10 баллов
            # ИСПРАВЛЕНО: учитываем направление (только рост)
            # ============================================================
            accel_score, acceleration = self.indicators.calculate_price_acceleration(df)
            if accel_score > 0:  # Только если ускорение вверх
                score += accel_score
                details['Acceleration'] = f"{acceleration:.1f}x (+{accel_score})"
            else:
                details['Acceleration'] = f"↓ {acceleration:.1f}x (+0)"
            
            # ============================================================
            # 6. TRADE COUNT - до 5 баллов
            # ============================================================
            trade_score, trade_growth = self.indicators.check_trade_count_growth(df)
            score += trade_score
            details['TradeCount'] = f"{trade_growth:.1f}x (+{trade_score})"
            
            # ============================================================
            # 7. FUNDING HISTORY - до 10 баллов
            # ИСПРАВЛЕНО: учитываем знак (положительный = бонус)
            # ============================================================
            funding_score, funding_change = self.indicators.check_funding_change(funding_df)
            score += funding_score
            current_funding = self.client.get_funding_rate(symbol)
            details['Funding'] = f"{current_funding*100:.4f}% (+{funding_score})"
            
            # ============================================================
            # 8. LIQUIDATIONS - до 15 баллов
            # ============================================================
            liq_score, liq_ratio = self.indicators.check_liquidations(liq_data)
            score += liq_score
            details['Liquidations'] = f"${liq_data['total']/1e6:.2f}M (+{liq_score})"
            
            # ============================================================
            # 9. VOLUME + OI SYNERGY - до 10 бонусных баллов
            # ИСПРАВЛЕНО: проверяем на ОДНОЙ СВЕЧЕ!
            # ============================================================
            synergy_score, synergy = self.indicators.check_volume_oi_synergy(df, oi_df, vol_ratio, oi_change)
            if synergy:
                score += synergy_score
                details['Synergy'] = f"✅ +{synergy_score} (бонус)"
            
            # ============================================================
            # 10. PUMP CONDITIONS - комплексная проверка
            # НОВЫЙ ИНДИКАТОР!
            # ============================================================
            pump_score, pump_conditions = self.indicators.check_pump_conditions(df, oi_df, vol_ratio, oi_change)
            if pump_score > 0:
                score += pump_score
                details['PumpCheck'] = f"✅ +{pump_score}"
            
            # ============================================================
            # ФИЛЬТРЫ
            # ============================================================
            
            # ATR (волатильность)
            atr_24h = self.indicators.calculate_atr(df, period=96)
            atr_4h = self.indicators.calculate_atr(df, period=48)
            
            if atr_24h > config.ATR_MAX_PERCENT_24H:
                return None
            if atr_4h > config.ATR_MAX_PERCENT_4H:
                return None
            
            # Сопротивление
            resistance, gap = self.indicators.find_resistance_levels(df, current_price)
            if gap < config.RESISTANCE_GAP_MIN:
                return None
            
            # ============================================================
            # ИТОГ
            # ============================================================
            if score >= config.SCORE_THRESHOLD:
                return {
                    'symbol': symbol,
                    'score': score,
                    'price': current_price,
                    'price_change': ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100,
                    'volume_ratio': vol_ratio,
                    'oi_change': oi_change,
                    'funding': current_funding,
                    'details': details,
                    'atr_24h': atr_24h,
                    'atr_4h': atr_4h,
                    'resistance_gap': gap,
                    'resistance': resistance,
                    'cvd': cvd_delta,
                    'bid_imbalance': bid_imbalance,
                    'acceleration': acceleration,
                    'liq_short': liq_data['short'],
                    'liq_long': liq_data['long'],
                    'synergy': synergy,
                    'pump_conditions': pump_conditions
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка check_pump {symbol}: {e}")
            return None