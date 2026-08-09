import json
import logging
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

def setup_logging():
    """Настройка логирования"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f'bot_{datetime.now().strftime("%Y%m%d")}.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


class SignalsHistory:
    """Класс для работы с историей сигналов"""
    
    def __init__(self):
        self.history_file = Path('data') / 'signals_history.json'
        self.history_file.parent.mkdir(exist_ok=True)
        self.data = self._load()
    
    def _load(self):
        """Загружает историю из файла"""
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return self._default_data()
        return self._default_data()
    
    def _default_data(self):
        """Возвращает структуру по умолчанию"""
        return {
            'signals': [],           # Все сигналы с результатами
            'stats': {
                'total': 0,
                'confirmed': 0,      # Отработали (да)
                'failed': 0,         # Не отработали (нет)
                'pending': 0,        # Ожидают ответа
                'accuracy': 0.0      # Точность в процентах
            }
        }
    
    def _save(self):
        """Сохраняет историю в файл"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False, default=str)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения истории: {e}")
            return False
    
    def add_signal(self, signal_data):
        """
        Добавляет новый сигнал в историю
        signal_data: dict с данными сигнала
        """
        signal_entry = {
            'id': len(self.data['signals']) + 1,
            'timestamp': datetime.now().isoformat(),
            'symbol': signal_data.get('symbol', ''),
            'score': signal_data.get('score', 0),
            'stage': signal_data.get('stage', 0),
            'stage_message': signal_data.get('stage_message', ''),
            'direction': signal_data.get('direction', 'NEUTRAL'),
            'price': signal_data.get('price', 0),
            'price_change': signal_data.get('price_change', 0),
            'volume_ratio': signal_data.get('volume_ratio', 0),
            'oi_change': signal_data.get('oi_change', 0),
            'resistance_gap': signal_data.get('resistance_gap', 0),
            'status': 'pending',  # pending, confirmed, failed
            'feedback_time': None,
            'feedback_comment': None
        }
        
        self.data['signals'].append(signal_entry)
        self.data['stats']['total'] += 1
        self.data['stats']['pending'] += 1
        self._save()
        return signal_entry['id']
    
    def update_signal_status(self, signal_id, status, comment=None):
        """
        Обновляет статус сигнала
        status: 'confirmed' или 'failed'
        """
        for signal in self.data['signals']:
            if signal['id'] == signal_id:
                if signal['status'] != 'pending':
                    return False, "Сигнал уже обработан"
                
                signal['status'] = status
                signal['feedback_time'] = datetime.now().isoformat()
                signal['feedback_comment'] = comment
                
                # Обновляем статистику
                self.data['stats']['pending'] -= 1
                if status == 'confirmed':
                    self.data['stats']['confirmed'] += 1
                else:
                    self.data['stats']['failed'] += 1
                
                # Пересчитываем точность
                total_answered = self.data['stats']['confirmed'] + self.data['stats']['failed']
                if total_answered > 0:
                    self.data['stats']['accuracy'] = round(
                        (self.data['stats']['confirmed'] / total_answered) * 100, 1
                    )
                
                self._save()
                return True, "Статус обновлён"
        
        return False, "Сигнал не найден"
    
    def get_stats(self):
        """Возвращает статистику"""
        return self.data['stats']
    
    def get_signal_by_id(self, signal_id):
        """Возвращает сигнал по ID"""
        for signal in self.data['signals']:
            if signal['id'] == signal_id:
                return signal
        return None
    
    def get_recent_signals(self, limit=10):
        """Возвращает последние N сигналов"""
        return self.data['signals'][-limit:][::-1]
    
    def get_stats_message(self):
        """Формирует сообщение со статистикой"""
        stats = self.data['stats']
        total = stats['total']
        
        if total == 0:
            return "📊 <b>Статистика сигналов</b>\n\nПока нет данных."
        
        confirmed = stats['confirmed']
        failed = stats['failed']
        pending = stats['pending']
        accuracy = stats['accuracy']
        
        # Определяем эмодзи для точности
        if accuracy >= 70:
            accuracy_emoji = "🟢"
        elif accuracy >= 50:
            accuracy_emoji = "🟡"
        else:
            accuracy_emoji = "🔴"
        
        message = f"""
📊 <b>СТАТИСТИКА СИГНАЛОВ</b>

📈 <b>Всего сигналов:</b> {total}
✅ <b>Отработали:</b> {confirmed}
❌ <b>Не отработали:</b> {failed}
⏳ <b>Ожидают ответа:</b> {pending}

🎯 <b>Точность:</b> {accuracy_emoji} {accuracy}%

─────────────────────
💡 Оценивайте сигналы, чтобы улучшать точность!
"""
        return message


# Глобальный экземпляр
signals_history = SignalsHistory()