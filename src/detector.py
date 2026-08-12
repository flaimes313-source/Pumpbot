import asyncio
from collections import deque
from datetime import datetime, timedelta
from config import config
from src.bybit_client import BybitClient
from src.indicators import Indicators
import logging

logger = logging.getLogger(__name__)

class PumpDetector:
    """Детектор пампов с двухстадийной системой и ПОЛНОСТЬЮ АСИНХРОННЫМ сканированием"""
    
    STAGE_1_THRESHOLD = 50
    STAGE_2_THRESHOLD = 70
    
    def __init__(self):
        self.client = BybitClient()
        self.indicators = Indicators()
        self.oi_history = {}
        self.results = []
        self.is_paused = False
    
    def pause(self):
        self.is_paused = True
        logger.info("⏸️ Сканирование поставлено на паузу")
    
    def resume(self):
        self.is_paused = False
        logger.info("▶️ Сканирование возобновлено")
    
    async def scan_all_symbols_async(self):
        """Асинхронное сканирование всех монет с параллельными запросами"""
        if self.is_paused:
            logger.info("⏸️ Сканирование на паузе")
            return []
        
        logger.info("="*50)
        logger.info("🚀 Начинаем асинхронное сканирование...")
        
        # Символы уже загружены в клиенте (кешированы)
        symbols = self.client.all_symbols
        if not symbols:
            logger.warning("⚠️ Символы не загружены, загружаем...")
            symbols = self.client.load_all_symbols()
            if not symbols:
                logger.error("❌ Не удалось загрузить символы")
                return []
        
        symbols_to_check = symbols[:config.MAX_SYMBOLS]
        logger.info(f"📊 Проверяем {len(symbols_to_check)} монет параллельно...")
        
        # ============================================================
        # ЗАПУСКАЕМ ПАРАЛЛЕЛЬНУЮ ПРОВЕРКУ ВСЕХ МОНЕТ
        # ============================================================
        tasks = [self._check_pump_async(symbol) for symbol in symbols_to_check]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        # ============================================================
        
        # Фильтруем результаты
        signals = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(f"❌ Ошибка {symbols_to_check[i]}: {result}")
                continue
            if result:
                signals.append(result)
                stage_emoji = "🟢" if result['stage'] == 2 else "🟡"
                direction_emoji = "🟢" if result['direction'] == 'LONG' else "🔴"
                logger.info(f"{stage_emoji} {result['symbol']}: {result['score']} баллов | {direction_emoji} {result['direction']}")
        
        signals.sort(key=lambda x: x['score'], reverse=True)
        logger.info(f"🏆 Найдено {len(signals)} сигналов!")
        return signals[:config.TOP_SIGNALS]
    
    async def _check_pump_async(self, symbol):
        """
        АСИНХРОННАЯ проверка одной монеты
        Все API запросы выполняются параллельно через asyncio.gather()
        """
        try:
            # ============================================================
            # ЗАПУСКАЕМ ВСЕ ЗАПРОСЫ ПАРАЛЛЕЛЬНО
            # ============================================================
            df_task = asyncio.to_thread(self.client.get_klines, symbol, '5', 200)
            oi_df_task = asyncio.to_thread(self.client.get_oi_history, symbol, 50)
            funding_df_task = asyncio.to_thread(self.client.get_funding_history, symbol, 30)
            orderbook_task = asyncio.to_thread(self.client.get_orderbook, symbol)
            liq_task = asyncio.to_thread(self.client.get_liquidations, symbol)
            volume_task = asyncio.to_thread(self.client.get_24h_volume_usd, symbol)
            funding_rate_task = asyncio.to_thread(self.client.get_funding_rate, symbol)
            # ============================================================
            
            # Ждём все запросы параллельно
            df, oi_df, funding_df, orderbook, liq_data, volume_usd, current_funding = await asyncio.gather(
                df_task, oi_df_task, funding_df_task, orderbook_task, liq_task, volume_task, funding_rate_task,
                return_exceptions=True
            )
            
            # Проверяем результаты
            if isinstance(df, Exception) or df.empty:
                return None
            
            if isinstance(volume_usd, Exception) or volume_usd < config.MIN_VOLUME_USD:
                return None
            
            current_price = df['close'].iloc[-1]
            price_change = ((df['close'].iloc[-1] - df['close'].iloc[-2]) / df['close'].iloc[-2]) * 100
            
            # ATR для динамических порогов
            atr = self.indicators.calculate_atr(df)
            
            score = 0
            details = {}
            
            # ============================================================
            # 1. VOLUME SPIKE
            # ============================================================
            vol_score, vol_ratio = self.indicators.check_volume_spike(df)
            score += vol_score
            details['Volume'] = f"{vol_ratio:.1f}x (+{vol_score})"
            
            # ============================================================
            # 2. OI GROWTH (с динамическими порогами)
            # ============================================================
            oi_score, oi_change = self.indicators.check_oi_growth(oi_df if not isinstance(oi_df, Exception) else None, atr)
            score += oi_score
            details['OI'] = f"+{oi_change:.1f}% (+{oi_score})"
            
            # ============================================================
            # 3. CVD
            # ============================================================
            cvd_score, cvd_delta = self.indicators.calculate_cvd(df)
            score += cvd_score
            details['CVD'] = f"{cvd_delta:.0f} (+{cvd_score})"
            
            # ============================================================
            # 4. BID/ASK
            # ============================================================
            bid_score, bid_imbalance = self.indicators.calculate_bid_ask_imbalance(
                orderbook if not isinstance(orderbook, Exception) else {}
            )
            score += bid_score
            details['Bid/Ask'] = f"{bid_imbalance:.1f}% (+{bid_score})"
            
            # ============================================================
            # 5. PRICE ACCELERATION
            # ============================================================
            accel_score, acceleration = self.indicators.calculate_price_acceleration(df)
            if accel_score > 0:
                score += accel_score
                details['Acceleration'] = f"{acceleration:.1f}x (+{accel_score})"
            else:
                details['Acceleration'] = f"↓ {acceleration:.1f}x (+0)"
            
            # ============================================================
            # 6. TRADE COUNT (из WebSocket)
            # ============================================================
            from src.trade_stream import trade_stream
            trade_ratio = trade_stream.get_trade_count_growth(symbol)
            trade_score, trade_growth = self.indicators.check_trade_count_growth(trade_ratio)
            score += trade_score
            details['TradeCount'] = f"{trade_growth:.1f}x (+{trade_score})"
            
            # ============================================================
            # 7. FUNDING
            # ============================================================
            funding_score, funding_change = self.indicators.check_funding_change(
                funding_df if not isinstance(funding_df, Exception) else None
            )
            score += funding_score
            details['Funding'] = f"{current_funding*100:.4f}% (+{funding_score})" if not isinstance(current_funding, Exception) else "N/A"
            
            # ============================================================
            # 8. LIQUIDATIONS
            # ============================================================
            liq_score, liq_ratio = self.indicators.check_liquidations(
                liq_data if not isinstance(liq_data, Exception) else {}
            )
            score += liq_score
            liq_total = liq_data.get('total', 0) if not isinstance(liq_data, Exception) else 0
            liq_long = liq_data.get('long', 0) if not isinstance(liq_data, Exception) else 0
            liq_short = liq_data.get('short', 0) if not isinstance(liq_data, Exception) else 0
            details['Liquidations'] = f"${liq_total/1e6:.2f}M (+{liq_score})"
            
            # ============================================================
            # 9. SYNERGY
            # ============================================================
            synergy_score, synergy = self.indicators.check_volume_oi_synergy(
                df, oi_df if not isinstance(oi_df, Exception) else None, vol_ratio, oi_change
            )
            if synergy:
                score += synergy_score
                details['Synergy'] = f"✅ +{synergy_score} (бонус)"
            
            # ============================================================
            # 10. PUMP CONDITIONS
            # ============================================================
            pump_score, pump_conditions = self.indicators.check_pump_conditions(df, oi_df if not isinstance(oi_df, Exception) else None, vol_ratio, oi_change)
            if pump_score > 0:
                score += pump_score
                details['PumpCheck'] = f"✅ +{pump_score}"
            
            # ============================================================
            # ФИЛЬТРЫ
            # ============================================================
            atr_24h = self.indicators.calculate_atr(df, period=96)
            atr_4h = self.indicators.calculate_atr(df, period=48)
            
            if atr_24h > config.ATR_MAX_PERCENT_24H:
                return None
            if atr_4h > config.ATR_MAX_PERCENT_4H:
                return None
            
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
            stage, stage_message = self._determine_stage(
                score, price_change, vol_ratio, oi_change, cvd_delta, bid_imbalance, direction
            )
            
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
                    'funding': current_funding if not isinstance(current_funding, Exception) else 0,
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
                    'trade_growth': trade_growth
                }
            
            return None
            
        except Exception as e:
            logger.error(f"❌ Ошибка _check_pump_async {symbol}: {e}")
            return None
    
    def _determine_direction(self, price_change, cvd_delta, bid_imbalance, liq_short, liq_long, oi_change):
        """Определение направления движения"""
        long_score = 0
        short_score = 0
        
        if price_change > 1.0:
            long_score += 20
        elif price_change < -1.0:
            short_score += 20
        
        if cvd_delta > 0:
            long_score += 15
        elif cvd_delta < 0:
            short_score += 15
        
        if bid_imbalance > 2:
            long_score += 10
        elif bid_imbalance < -2:
            short_score += 10
        
        if liq_short > liq_long * 1.5:
            long_score += 15
        elif liq_long > liq_short * 1.5:
            short_score += 15
        
        if oi_change > 3 and price_change > 0:
            long_score += 10
        elif oi_change > 3 and price_change < 0:
            short_score += 10
        
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
    
    def _determine_stage(self, score, price_change, vol_ratio, oi_change, cvd_delta, bid_imbalance, direction):
        """Определение стадии"""
        stage_1_conditions = (
            vol_ratio > 1.5 and
            oi_change > 3 and
            abs(price_change) < 2.0 and
            abs(cvd_delta) > 0
        )
        
        stage_2_conditions = (
            abs(price_change) > 2.0 and
            vol_ratio > 2.0 and
            oi_change > 5 and
            abs(cvd_delta) > 0 and
            abs(bid_imbalance) > 0
        )
        
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
        else:
            stage = 0
            stage_message = ""
        
        return stage, stage_message