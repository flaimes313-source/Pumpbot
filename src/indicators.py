import pandas as pd
import numpy as np
from config import config
import logging

logger = logging.getLogger(__name__)

class Indicators:
    """Расчёт всех индикаторов с динамическими порогами"""
    
    @staticmethod
    def calculate_atr(df, period=14):
        """ATR в процентах от цены"""
        if df.empty or len(df) < period:
            return 999.0
        
        try:
            high = pd.to_numeric(df['high'], errors='coerce')
            low = pd.to_numeric(df['low'], errors='coerce')
            close = pd.to_numeric(df['close'], errors='coerce')
            
            tr1 = high - low
            tr2 = (high - close.shift(1)).abs()
            tr3 = (low - close.shift(1)).abs()
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
            
            atr = tr.rolling(period).mean().iloc[-1]
            price = close.iloc[-1]
            
            if price > 0 and atr > 0:
                return (atr / price) * 100
        except Exception as e:
            logger.error(f"Ошибка ATR: {e}")
        
        return 999.0
    
    @staticmethod
    def get_dynamic_thresholds(df, base_threshold, atr_period=14, multiplier=1.0):
        """
        Возвращает динамические пороги на основе ATR
        """
        atr = Indicators.calculate_atr(df, atr_period)
        if atr == 999.0:
            return base_threshold
        
        # Чем выше волатильность - тем выше порог
        dynamic_threshold = base_threshold * (1 + (atr / 10) * multiplier)
        return min(dynamic_threshold, base_threshold * 3)  # Не более чем в 3 раза
    
    @staticmethod
    def check_volume_spike(df):
        """Всплеск объёма (последняя свеча vs средний)"""
        if df.empty or len(df) < 31:
            return 0, 0.0
        
        try:
            volume = pd.to_numeric(df['volume'], errors='coerce')
            last_volume = volume.iloc[-1]
            avg_volume = volume.iloc[-31:-1].mean()
            
            if avg_volume > 0 and last_volume > 0:
                ratio = last_volume / avg_volume
                
                # Динамические пороги на основе ATR
                atr = Indicators.calculate_atr(df)
                dynamic_30 = 3.0 * (1 + atr / 20)
                dynamic_20 = 2.0 * (1 + atr / 20)
                
                if ratio > dynamic_30:
                    return 30, ratio
                elif ratio > dynamic_20:
                    return 20, ratio
        except Exception as e:
            logger.error(f"Ошибка volume spike: {e}")
        
        return 0, 0.0
    
    @staticmethod
    def check_oi_growth(oi_df, atr=None):
        """
        Проверка роста OI с динамическими порогами
        """
        if oi_df.empty or len(oi_df) < 7:
            return 0, 0.0
        
        try:
            oi = pd.to_numeric(oi_df['openInterest'], errors='coerce')
            current_oi = oi.iloc[-1]
            
            if current_oi <= 0:
                return 0, 0.0
            
            # Базовые пороги
            base_thresholds = {'5min': 3, '15min': 5, '30min': 7}
            
            # Корректируем на основе ATR
            if atr and atr != 999.0:
                multiplier = 1 + atr / 15
            else:
                multiplier = 1.0
            
            periods = {'5min': 1, '15min': 3, '30min': 6}
            total_score = 0
            max_change = 0.0
            
            for period_name, period_candles in periods.items():
                if len(oi) > period_candles:
                    past_oi = oi.iloc[-period_candles - 1]
                    if past_oi > 0:
                        change = ((current_oi - past_oi) / past_oi) * 100
                        max_change = max(max_change, change)
                        
                        threshold = base_thresholds[period_name] * multiplier
                        
                        if period_name == '5min' and change > threshold:
                            total_score += 10
                        elif period_name == '15min' and change > threshold * 1.2:
                            total_score += 8
                        elif period_name == '30min' and change > threshold * 1.4:
                            total_score += 7
            
            return min(total_score, 25), max_change
        except Exception as e:
            logger.error(f"Ошибка OI growth: {e}")
        
        return 0, 0.0
    
    # Остальные методы без изменений...
    @staticmethod
    def calculate_cvd(df):
        """Cumulative Volume Delta"""
        if df.empty or len(df) < 2:
            return 0, 0.0
        
        try:
            close = pd.to_numeric(df['close'], errors='coerce')
            open_price = pd.to_numeric(df['open'], errors='coerce')
            volume = pd.to_numeric(df['volume'], errors='coerce')
            
            valid_mask = ~(close.isna() | open_price.isna() | volume.isna())
            if not valid_mask.any():
                return 0, 0.0
            
            close = close[valid_mask]
            open_price = open_price[valid_mask]
            volume = volume[valid_mask]
            
            delta = []
            for i in range(len(close)):
                if close.iloc[i] > open_price.iloc[i]:
                    delta.append(volume.iloc[i])
                elif close.iloc[i] < open_price.iloc[i]:
                    delta.append(-volume.iloc[i])
                else:
                    delta.append(0)
            
            if not delta:
                return 0, 0.0
            
            cvd = np.cumsum(delta)
            
            if len(cvd) >= 2:
                cvd_change = cvd[-1] - cvd[-3] if len(cvd) >= 3 else cvd[-1] - cvd[0]
                if volume.iloc[-1] > 0:
                    score = min(15, max(0, abs(cvd_change) / volume.iloc[-1] * 100))
                    return score, cvd_change
        except Exception as e:
            logger.error(f"Ошибка CVD: {e}")
        
        return 0, 0.0
    
    @staticmethod
    def calculate_bid_ask_imbalance(orderbook):
        """Дисбаланс Bid/Ask в стакане (Top 25)"""
        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])
        
        if not bids or not asks:
            return 0, 0.0
        
        try:
            bid_volume = sum([float(b[1]) for b in bids[:25] if len(b) > 1])
            ask_volume = sum([float(a[1]) for a in asks[:25] if len(a) > 1])
            
            total_volume = bid_volume + ask_volume
            if total_volume > 0:
                imbalance = (bid_volume - ask_volume) / total_volume * 100
                score = min(10, max(0, abs(imbalance) / 5))
                return score, imbalance
        except Exception as e:
            logger.error(f"Ошибка Bid/Ask: {e}")
        
        return 0, 0.0
    
    @staticmethod
    def calculate_price_acceleration(df):
        """Ускорение цены с учётом направления"""
        if df.empty or len(df) < 5:
            return 0, 0.0
        
        try:
            close = pd.to_numeric(df['close'], errors='coerce')
            
            price_5m = close.iloc[-1] - close.iloc[-2]
            price_4m = close.iloc[-2] - close.iloc[-3]
            price_3m = close.iloc[-3] - close.iloc[-4]
            price_2m = close.iloc[-4] - close.iloc[-5]
            
            avg_speed = (price_2m + price_3m + price_4m) / 3
            
            if avg_speed > 0:
                acceleration = price_5m / avg_speed
                if price_5m > 0 and acceleration > 1.2:
                    if acceleration > 2.0:
                        return 10, acceleration
                    elif acceleration > 1.5:
                        return 7, acceleration
                    elif acceleration > 1.2:
                        return 5, acceleration
            elif price_5m < 0:
                return 0, -abs(price_5m / avg_speed) if avg_speed != 0 else 0
                
        except Exception as e:
            logger.error(f"Ошибка price acceleration: {e}")
        
        return 0, 1.0
    
    @staticmethod
    def check_trade_count_growth(trade_ratio):
        """
        Рост количества сделок (используем реальные данные из WebSocket)
        """
        try:
            if trade_ratio > 2.0:
                return 5, trade_ratio
            elif trade_ratio > 1.5:
                return 3, trade_ratio
        except Exception as e:
            logger.error(f"Ошибка trade count: {e}")
        
        return 0, 1.0
    
    @staticmethod
    def check_funding_change(funding_df):
        """Реальное изменение funding rate с учётом знака"""
        if funding_df.empty or len(funding_df) < 3:
            return 0, 0.0
        
        try:
            funding = pd.to_numeric(funding_df['fundingRate'], errors='coerce')
            current = funding.iloc[-1]
            
            if pd.isna(current):
                return 0, 0.0
            
            past_3 = funding.iloc[-3] if len(funding) >= 3 else current
            past_6 = funding.iloc[-6] if len(funding) >= 6 else past_3
            
            change_3 = (current - past_3) * 100
            change_6 = (current - past_6) * 100
            
            score = 0
            if current > 0 and change_3 > 0.005:
                score += 5
            if current > 0 and change_6 > 0.01:
                score += 5
            if current < 0:
                score -= 3
            
            return max(0, min(score, 10)), max(change_3, change_6)
        except Exception as e:
            logger.error(f"Ошибка funding change: {e}")
        
        return 0, 0.0
    
    @staticmethod
    def check_volume_oi_synergy(df, oi_df, volume_ratio, oi_change):
        """Синергия объёма и OI на одной свече"""
        if df.empty or oi_df.empty:
            return 0, False
        
        try:
            last_volume = pd.to_numeric(df['volume'], errors='coerce').iloc[-1]
            prev_volume = pd.to_numeric(df['volume'], errors='coerce').iloc[-2]
            
            last_oi = pd.to_numeric(oi_df['openInterest'], errors='coerce').iloc[-1]
            prev_oi = pd.to_numeric(oi_df['openInterest'], errors='coerce').iloc[-2]
            
            volume_change = (last_volume - prev_volume) / prev_volume * 100 if prev_volume > 0 else 0
            oi_change_single = (last_oi - prev_oi) / prev_oi * 100 if prev_oi > 0 else 0
            
            if volume_change > 20 and oi_change_single > 2:
                return 10, True
            elif volume_change > 10 and oi_change_single > 1:
                return 5, True
                
        except Exception as e:
            logger.error(f"Ошибка synergy: {e}")
        
        return 0, False
    
    @staticmethod
    def check_liquidations(liq_data):
        """Оценка ликвидаций"""
        total = liq_data.get('total', 0)
        long = liq_data.get('long', 0)
        short = liq_data.get('short', 0)
        
        if total == 0:
            return 0, 0.0
        
        try:
            score = 0
            if total > 1_000_000:
                score += 10
            elif total > 500_000:
                score += 7
            elif total > 200_000:
                score += 4
            
            if short > long * 1.5:
                score += 5
            elif long > short * 1.5:
                score -= 3
            
            return max(0, min(score, 15)), (short - long) / (short + long) if (short + long) > 0 else 0
        except Exception as e:
            logger.error(f"Ошибка liquidations: {e}")
        
        return 0, 0.0
    
    @staticmethod
    def find_resistance_levels(df, current_price, lookback=50):
        """Нахождение уровней сопротивления"""
        if df.empty or len(df) < lookback:
            return current_price * 1.1, 10.0
        
        try:
            highs = pd.to_numeric(df['high'], errors='coerce').values
            highs = highs[~np.isnan(highs)]
            
            if len(highs) < lookback:
                return current_price * 1.1, 10.0
            
            resistance_levels = []
            for i in range(10, len(highs) - 10):
                if highs[i] == max(highs[i-10:i+10]):
                    resistance_levels.append(highs[i])
            
            if not resistance_levels:
                return current_price * 1.1, 10.0
            
            resistance_levels = sorted([r for r in resistance_levels if r > current_price])
            
            if resistance_levels:
                nearest = resistance_levels[0]
                gap = ((nearest - current_price) / current_price) * 100
                return nearest, gap
        except Exception as e:
            logger.error(f"Ошибка resistance levels: {e}")
        
        return current_price * 1.1, 10.0
    
    @staticmethod
    def check_pump_conditions(df, oi_df, volume_ratio, oi_change):
        """Комплексная проверка условий для пампов"""
        if df.empty:
            return 0, False
        
        try:
            close = pd.to_numeric(df['close'], errors='coerce')
            volume = pd.to_numeric(df['volume'], errors='coerce')
            
            price_change = (close.iloc[-1] - close.iloc[-2]) / close.iloc[-2] * 100 if close.iloc[-2] > 0 else 0
            
            conditions = {
                'price_up': price_change > 1.0,
                'volume_up': volume_ratio > 1.5,
                'oi_up': oi_change > 3,
                'cvd_up': True,
            }
            
            score = 0
            if conditions['price_up']:
                score += 5
            if conditions['volume_up']:
                score += 5
            if conditions['oi_up']:
                score += 5
            
            if score >= 10:
                score += 5
            
            return score, conditions
            
        except Exception as e:
            logger.error(f"Ошибка pump conditions: {e}")
        
        return 0, False