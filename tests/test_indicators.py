import unittest
import pandas as pd
import numpy as np
from src.indicators import Indicators

class TestIndicators(unittest.TestCase):
    
    def setUp(self):
        """Создаём тестовые данные"""
        self.df = pd.DataFrame({
            'high': np.random.uniform(100, 110, 50),
            'low': np.random.uniform(95, 100, 50),
            'close': np.random.uniform(98, 105, 50),
            'volume': np.random.uniform(1000, 5000, 50)
        })
    
    def test_atr_calculation(self):
        """Тест расчёта ATR"""
        atr = Indicators.calculate_atr(self.df)
        self.assertGreater(atr, 0)
        self.assertLess(atr, 20)  # ATR должен быть разумным
    
    def test_volume_spike(self):
        """Тест всплеска объёма"""
        # Искусственно создаём всплеск
        self.df.loc[49, 'volume'] = 100000
        score, ratio = Indicators.check_volume_spike(self.df)
        self.assertGreater(score, 0)
        self.assertGreater(ratio, 1)

if __name__ == '__main__':
    unittest.main()