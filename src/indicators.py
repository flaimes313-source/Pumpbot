import pandas as pd
import numpy as np
from config import config
import logging

logger = logging.getLogger(__name__)

class Indicators:
    """Расчёт индикаторов"""
    
    @staticmethod
    def calculate_atr(df, period=14):
        """ATR в процентах от цены"""
        if len(df) < period:
            return 999.0
        
        high = df['high']
        low = df['low']
        close = df['close'].shift(1)
        
        tr1 = high - low
        tr2 = (high - close).abs()
        tr3 = (low - close).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        atr = tr.rolling(period).mean().iloc[-1]
        price = df['close'].iloc[-1]
        
        return (atr / price) * 100
    
    @staticmethod
    def check_volume_spike(df):
        """Проверка всплеска объёма"""
        if len(df) < 31:
            return 0, 0.0
        
        last_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].iloc[-31:-1].mean()
        
        if avg_volume > 0:
            ratio = last_volume / avg_volume
            if ratio > config.VOLUME_RATIO_30:
                return 30, ratio
            elif ratio > config.VOLUME_RATIO_20:
                return 20, ratio
        return 0, 0.0
    
    @staticmethod
    def find_resistance_levels(df, current_price, lookback=50):
        """Нахождение уровней сопротивления"""
        if len(df) < lookback:
            return current_price * 1.1, 10.0
        
        highs = df['high'].values
        resistance_levels = []
        
        for i in range(10, len(highs) - 10):
            if highs[i] == max(highs[i-10:i+10]):
                resistance_levels.append(highs[i])
        
        if not resistance_levels:
            return current_price * 1.1, 10.0
        
        # Ближайший уровень выше текущей цены
        resistance_levels = sorted([r for r in resistance_levels if r > current_price])
        
        if resistance_levels:
            nearest = resistance_levels[0]
            gap = ((nearest - current_price) / current_price) * 100
            return nearest, gap
        else:
            return current_price * 1.1, 10.0