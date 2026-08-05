from collections import deque
from datetime import datetime, timedelta
from config import config
from src.bybit_client import BybitClient
from src.indicators import Indicators
import logging

logger = logging.getLogger(__name__)

class PumpDetector:
    """Детектор пампов с двухстадийной системой и определением направления"""
    
    # Пороги для стадий
    STAGE_1_THRESHOLD = 50   # Раннее предупреждение
    STAGE_2_THRESHOLD = 70   # Памп подтвержден
    
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
                    stage_emoji = "🟢" if result['stage'] == 2 else "🟡"
                    direction_emoji = "🟢" if result['direction'] == 'LONG' else "🔴"
                    logger.info(f"{stage_emoji} [{i}] {symbol}: {result['score']} баллов | {direction_emoji} {result['direction']}")
                elif i % 10 == 0:
                    logger.info(f"⏳ Проверено {i}/{len(symbols_to_check)}")
            except Exception as e:
                logger.error(f"❌ Ошибка {symbol}: {e}")
        
        results.sort(key=lambda x: x['score'], reverse=True)
        logger.info(f"🏆 Найдено {len(results)} сигналов!")
        return results[:config.TOP_SIGNALS]
    
    def _determine_direction(self, price_change, cvd_delta, bid_imbalance, liq_short, liq_long, oi_change):
        """
        Определение направления движения:
        - LONG: памп вверх
        - SHORT: дамп вниз
        - NEUTRAL: неопределенно
        """
        long_score = 0
        short_score = 0
        
        # 1. Изменение цены
        if price_change > 1.0:
            long_score += 20
        elif price_change < -1.0:
            short_score += 20
        
        # 2. CVD (агрессивные покупки/продажи)
        if cvd_delta > 0:
            long_score += 15
        elif cvd_delta < 0:
            short_score += 15
        
        # 3. Bid/Ask дисбаланс
        if bid_imbalance > 2:
            long_score += 10
        elif bid_imbalance < -2:
            short_score += 10
        
        # 4. Ликвидации (преобладание шортов = бычий сигнал)
        if liq_short > liq_long * 1.5:
            long_score += 15  # Шорты ликвидируют = цена идёт вверх
        elif liq_long > liq_short * 1.5:
            short_score += 15  # Лонги ликвидируют = цена идёт вниз
        
        # 5. OI (рост при росте цены = бычий сигнал)
        if oi_change > 3 and price_change > 0:
            long_score += 10
        elif oi_change > 3 and price_change < 0:
            short_score += 10
        
        # Определяем направление
        if long_score > short_score + 10:
            return "LONG", long_score, short_score
        elif short_score > long_score + 10:
            return "SHORT", long_score, short_score
        elif price_change > 1.0:
            return "LONG", long_score, short_score
        elif price_change < -1.0:
            return "SHORT", long_score, short_score
        else:
            return "NEUTRAL", long_score, short_score
    
    def check_pump(self, symbol):
        """Проверка одной монеты с двухстадийной системой"""
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
            price_change = ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
            
            score = 0
            details = {}
            
            # ============================================================
            # 1. VOLUME SPIKE (до 30 баллов)
            # ============================================================
            vol_score, vol_ratio = self.indicators.check_volume_spike(df)
            score += vol_score
            details['Volume'] = f"{vol_ratio:.1f}x (+{vol_score})"
            
            # ============================================================
            # 2. OI GROWTH (до 25 баллов)
            # ============================================================
            oi_score, oi_change = self.indicators.check_oi_growth(oi_df)
            score += oi_score
            details['OI'] = f"+{oi_change:.1f}% (+{oi_score})"
            
            # ============================================================
            # 3. CVD (до 15 баллов)
            # ============================================================
            cvd_score, cvd_delta = self.indicators.calculate_cvd(df)
            score += cvd_score
            details['CVD'] = f"{cvd_delta:.0f} (+{cvd_score})"
            
            # ============================================================
            # 4. BID/ASK IMBALANCE (до 10 баллов)
            # ============================================================
            bid_score, bid_imbalance = self.indicators.calculate_bid_ask_imbalance(orderbook)
            score += bid_score
            details['Bid/Ask'] = f"{bid_imbalance:.1f}% (+{bid_score})"
            
            # ============================================================
            # 5. PRICE ACCELERATION (до 10 баллов)
            # ============================================================
            accel_score, acceleration = self.indicators.calculate_price_acceleration(df)
            if accel_score > 0:
                score += accel_score
                details['Acceleration'] = f"{acceleration:.1f}x (+{accel_score})"
            else:
                details['Acceleration'] = f"↓ {acceleration:.1f}x (+0)"
            
            # ============================================================
            # 6. TRADE COUNT (до 5 баллов)
            # ============================================================
            trade_score, trade_growth = self.indicators.check_trade_count_growth(df)
            score += trade_score
            details['TradeCount'] = f"{trade_growth:.1f}x (+{trade_score})"
            
            # ============================================================
            # 7. FUNDING (до 10 баллов)
            # ============================================================
            funding_score, funding_change = self.indicators.check_funding_change(funding_df)
            score += funding_score
            current_funding = self.client.get_funding_rate(symbol)
            details['Funding'] = f"{current_funding*100:.4f}% (+{funding_score})"
            
            # ============================================================
            # 8. LIQUIDATIONS (до 15 баллов)
            # ============================================================
            liq_score, liq_ratio = self.indicators.check_liquidations(liq_data)
            score += liq_score
            liq_total = liq_data.get('total', 0)
            liq_long = liq_data.get('long', 0)
            liq_short = liq_data.get('short', 0)
            details['Liquidations'] = f"${liq_total/1e6:.2f}M (+{liq_score})"
            
            # ============================================================
            # 9. SYNERGY (до 10 баллов)
            # ============================================================
            synergy_score, synergy = self.indicators.check_volume_oi_synergy(df, oi_df, vol_ratio, oi_change)
            if synergy:
                score += synergy_score
                details['Synergy'] = f"✅ +{synergy_score} (бонус)"
            
            # ============================================================
            # 10. PUMP CONDITIONS (до 15 баллов)
            # ============================================================
            pump_score, pump_conditions = self.indicators.check_pump_conditions(df, oi_df, vol_ratio, oi_change)
            if pump_score > 0:
                score += pump_score
                details['PumpCheck'] = f"✅ +{pump_score}"
            
            # ============================================================
            # ФИЛЬТРЫ
            # ============================================================
            
            # ATR
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
            # ОПРЕДЕЛЕНИЕ НАПРАВЛЕНИЯ
            # ============================================================
            direction, long_score, short_score = self._determine_direction(
                price_change, cvd_delta, bid_imbalance, liq_short, liq_long, oi_change
            )
            
            # ============================================================
            # ОПРЕДЕЛЕНИЕ СТАДИИ
            # ============================================================
            
            # Стадия 1: Раннее предупреждение
            stage_1_conditions = (
                vol_ratio > 1.5 and
                oi_change > 3 and
                abs(price_change) < 2.0 and
                abs(cvd_delta) > 0
            )
            
            # Стадия 2: Памп подтвержден
            stage_2_conditions = (
                abs(price_change) > 2.0 and
                vol_ratio > 2.0 and
                oi_change > 5 and
                abs(cvd_delta) > 0 and
                abs(bid_imbalance) > 0
            )
            
            # Определяем стадию
            stage = 0
            stage_message = ""
            
            if score >= self.STAGE_2_THRESHOLD and stage_2_conditions:
                stage = 2
                if direction == "LONG":
                    stage_message = "🚀 ПАМП ПОДТВЕРЖДЕН!"
                elif direction == "SHORT":
                    stage_message = "💥 ДАМП ПОДТВЕРЖДЕН!"
                else:
                    stage_message = "🚀 ДВИЖЕНИЕ ПОДТВЕРЖДЕНО!"
            elif score >= self.STAGE_1_THRESHOLD and stage_1_conditions:
                stage = 1
                if direction == "LONG":
                    stage_message = "🟡 ВОЗМОЖЕН ПАМП. НАЧИНАЕТСЯ НАКОПЛЕНИЕ."
                elif direction == "SHORT":
                    stage_message = "🟡 ВОЗМОЖЕН ДАМП. НАЧИНАЕТСЯ РАЗВОРОТ."
                else:
                    stage_message = "🟡 ВОЗМОЖНО ДВИЖЕНИЕ. НАБЛЮДАЙТЕ."
            elif score >= self.STAGE_2_THRESHOLD and not stage_2_conditions:
                if abs(price_change) > 2.0 and vol_ratio > 2.0:
                    stage = 2
                    if direction == "LONG":
                        stage_message = "🚀 ПАМП ПОДТВЕРЖДЕН!"
                    elif direction == "SHORT":
                        stage_message = "💥 ДАМП ПОДТВЕРЖДЕН!"
                    else:
                        stage_message = "🚀 ДВИЖЕНИЕ ПОДТВЕРЖДЕНО!"
                else:
                    stage = 1
                    if direction == "LONG":
                        stage_message = "🟡 ВОЗМОЖЕН ПАМП. НАБЛЮДАЙТЕ."
                    elif direction == "SHORT":
                        stage_message = "🟡 ВОЗМОЖЕН ДАМП. НАБЛЮДАЙТЕ."
                    else:
                        stage_message = "🟡 ВОЗМОЖНО ДВИЖЕНИЕ."
            
            # Если есть сигнал - возвращаем
            if stage > 0:
                return {
                    'symbol': symbol,
                    'score': score,
                    'stage': stage,
                    'stage_message': stage_message,
                    'direction': direction,
                    'long_score': long_score,
                    'short_score': short_score,
                    'price': current_price,
                    'price_change': price_change,
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
                    'liq_short': liq_short,
                    'liq_long': liq_long,
                    'liq_total': liq_total,
                    'synergy': synergy,
                    'pump_conditions': pump_conditions,
                    'stage_1_conditions': stage_1_conditions,
                    'stage_2_conditions': stage_2_conditions
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка check_pump {symbol}: {e}")
            return None