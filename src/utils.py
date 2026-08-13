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
    """Класс для работы с историей сигналов (индивидуально для каждого пользователя)"""
    
    def __init__(self):
        self.history_dir = Path('data')
        self.history_dir.mkdir(exist_ok=True)
        self.current_chat_id = None
        self.data = None
        self.history_file = None
    
    def _get_user_file(self, chat_id):
        return self.history_dir / f'signals_history_{chat_id}.json'
    
    def set_user(self, chat_id):
        self.current_chat_id = chat_id
        self.history_file = self._get_user_file(chat_id)
        self.data = self._load()
        return self
    
    def _default_data(self):
        return {
            'signals': [],
            'stats': {
                'total': 0,
                'confirmed': 0,
                'failed': 0,
                'pending': 0,
                'deleted': 0,
                'accuracy': 0.0
            }
        }
    
    def _ensure_file_exists(self):
        if not self.history_file.exists():
            logger.info(f"📁 Файл истории для пользователя {self.current_chat_id} не найден, создаю новый...")
            self.data = self._default_data()
            self._save()
            logger.info(f"✅ Файл истории создан: {self.history_file}")
            return True
        return False
    
    def _load(self):
        if self.history_file is None:
            return self._default_data()
        
        self._ensure_file_exists()
        
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                stats = data.get('stats', {})
                default_stats = self._default_data()['stats']
                
                need_update = False
                for key in default_stats:
                    if key not in stats:
                        stats[key] = default_stats[key]
                        need_update = True
                
                if need_update:
                    data['stats'] = stats
                    self._save(data)
                    logger.info("✅ Структура файла истории обновлена")
                
                return data
                
        except Exception as e:
            logger.error(f"Ошибка загрузки файла истории: {e}")
            return self._default_data()
    
    def _save(self, data=None):
        if self.history_file is None:
            return False
        
        try:
            if data is None:
                data = self.data
            
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения истории: {e}")
            return False
    
    def add_signal(self, signal_data):
        if self.data is None:
            return None
        
        self._ensure_file_exists()
        
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
            'status': 'pending',
            'feedback_time': None,
            'feedback_comment': None
        }
        
        self.data['signals'].append(signal_entry)
        self.data['stats']['total'] += 1
        self.data['stats']['pending'] += 1
        self._save()
        return signal_entry['id']
    
    def update_signal_status(self, signal_id, status, comment=None):
        if self.data is None:
            return False, "Пользователь не задан"
        
        for signal in self.data['signals']:
            if signal['id'] == signal_id:
                if signal['status'] != 'pending' and status != 'deleted':
                    return False, "Сигнал уже обработан"
                
                old_status = signal['status']
                signal['status'] = status
                signal['feedback_time'] = datetime.now().isoformat()
                signal['feedback_comment'] = comment
                
                if status == 'deleted':
                    if old_status == 'pending':
                        self.data['stats']['pending'] -= 1
                    elif old_status == 'confirmed':
                        self.data['stats']['confirmed'] -= 1
                    elif old_status == 'failed':
                        self.data['stats']['failed'] -= 1
                    self.data['stats']['deleted'] += 1
                else:
                    if old_status == 'pending':
                        self.data['stats']['pending'] -= 1
                    elif old_status == 'confirmed':
                        self.data['stats']['confirmed'] -= 1
                    elif old_status == 'failed':
                        self.data['stats']['failed'] -= 1
                    
                    if status == 'confirmed':
                        self.data['stats']['confirmed'] += 1
                    elif status == 'failed':
                        self.data['stats']['failed'] += 1
                
                total_answered = self.data['stats']['confirmed'] + self.data['stats']['failed']
                if total_answered > 0:
                    self.data['stats']['accuracy'] = round(
                        (self.data['stats']['confirmed'] / total_answered) * 100, 1
                    )
                else:
                    self.data['stats']['accuracy'] = 0.0
                
                self._save()
                return True, "Статус обновлён"
        
        return False, "Сигнал не найден"
    
    def get_stats(self):
        if self.data is None:
            return self._default_data()['stats']
        return self.data['stats']
    
    def get_signal_by_id(self, signal_id):
        if self.data is None:
            return None
        for signal in self.data['signals']:
            if signal['id'] == signal_id:
                return signal
        return None
    
    def get_recent_signals(self, limit=10):
        if self.data is None:
            return []
        return self.data['signals'][-limit:][::-1]
    
    def get_stats_message(self):
        if self.data is None:
            return "📊 <b>Статистика сигналов</b>\n\nПока нет данных."
        
        stats = self.data['stats']
        total = stats['total'] - stats['deleted']
        
        if total == 0:
            return "📊 <b>Статистика сигналов</b>\n\nПока нет данных."
        
        confirmed = stats['confirmed']
        failed = stats['failed']
        pending = stats['pending']
        deleted = stats['deleted']
        accuracy = stats['accuracy']
        
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
🗑️ <b>Удалено:</b> {deleted}

🎯 <b>Точность:</b> {accuracy_emoji} {accuracy}%

─────────────────────
💡 Оценивайте сигналы, чтобы улучшать точность!
"""
        return message


class SubscribersManager:
    """Класс для управления подписчиками с сохранением в файл (СИНГЛТОН)"""
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SubscribersManager, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, admin_chat_id=None):
        # Проверяем, был ли уже инициализирован
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        self.subscribers_file = Path('data') / 'subscribers.json'
        self.subscribers_file.parent.mkdir(exist_ok=True)
        self.subscribers = {}
        self.admin_chat_id = admin_chat_id
        self._load()
        self._ensure_admin_exists()
        logger.info(f"📊 SubscribersManager инициализирован, загружено {len(self.subscribers)} подписчиков")
    
    def _ensure_admin_exists(self):
        """Автоматически добавляет администратора в список подписчиков при запуске"""
        if self.admin_chat_id is None:
            return
        
        admin_id_str = str(self.admin_chat_id)
        
        if admin_id_str not in self.subscribers:
            logger.info(f"👤 Добавляю администратора {self.admin_chat_id} в подписчики...")
            self.subscribers[admin_id_str] = {
                'chat_id': self.admin_chat_id,
                'username': 'admin',
                'first_name': 'Administrator',
                'last_name': '',
                'subscribed_at': datetime.now().isoformat(),
                'last_active': datetime.now().isoformat(),
                'is_blocked': False
            }
            self._save()
            logger.info(f"✅ Администратор {self.admin_chat_id} добавлен и разблокирован")
        else:
            if self.subscribers[admin_id_str].get('is_blocked', False):
                self.subscribers[admin_id_str]['is_blocked'] = False
                self._save()
                logger.info(f"🔓 Администратор {self.admin_chat_id} разблокирован")
    
    def _load(self):
        """Загружает подписчиков из файла"""
        if self.subscribers_file.exists():
            try:
                with open(self.subscribers_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.subscribers = data.get('users', {})
                    logger.info(f"✅ Загружено {len(self.subscribers)} подписчиков из файла")
                    return
            except Exception as e:
                logger.error(f"Ошибка загрузки подписчиков: {e}")
        
        self.subscribers = {}
        self._save()
    
    def _save(self):
        """Сохраняет подписчиков в файл"""
        try:
            data = {
                'users': self.subscribers,
                'total': len(self.subscribers),
                'last_updated': datetime.now().isoformat()
            }
            with open(self.subscribers_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False, default=str)
            return True
        except Exception as e:
            logger.error(f"Ошибка сохранения подписчиков: {e}")
            return False
    
    def add_subscriber(self, chat_id, username=None, first_name=None, last_name=None):
        """Добавляет подписчика"""
        chat_id_str = str(chat_id)
        
        if chat_id_str in self.subscribers:
            self.subscribers[chat_id_str]['last_active'] = datetime.now().isoformat()
            if username:
                self.subscribers[chat_id_str]['username'] = username
            if first_name:
                self.subscribers[chat_id_str]['first_name'] = first_name
            self._save()
            return False
        
        self.subscribers[chat_id_str] = {
            'chat_id': chat_id,
            'username': username or 'unknown',
            'first_name': first_name or 'unknown',
            'last_name': last_name or '',
            'subscribed_at': datetime.now().isoformat(),
            'last_active': datetime.now().isoformat(),
            'is_blocked': True
        }
        self._save()
        logger.info(f"✅ Новый подписчик: {username or chat_id}")
        return True
    
    def remove_subscriber(self, chat_id):
        """Удаляет подписчика"""
        chat_id_str = str(chat_id)
        if chat_id_str in self.subscribers:
            del self.subscribers[chat_id_str]
            self._save()
            logger.info(f"❌ Подписчик {chat_id} удалён")
            return True
        return False
    
    def block_subscriber(self, chat_id):
        """Блокирует подписчика (временно)"""
        chat_id_str = str(chat_id)
        if chat_id_str in self.subscribers:
            self.subscribers[chat_id_str]['is_blocked'] = True
            self._save()
            logger.info(f"🚫 Подписчик {chat_id} заблокирован")
            return True
        return False
    
    def unblock_subscriber(self, chat_id):
        """Разблокирует подписчика"""
        chat_id_str = str(chat_id)
        if chat_id_str in self.subscribers:
            self.subscribers[chat_id_str]['is_blocked'] = False
            self._save()
            logger.info(f"✅ Подписчик {chat_id} разблокирован")
            return True
        return False
    
    def get_subscribers(self):
        return self.subscribers
    
    def get_subscribers_count(self):
        return len(self.subscribers)
    
    def is_subscribed(self, chat_id):
        return str(chat_id) in self.subscribers
    
    def is_blocked(self, chat_id):
        chat_id_str = str(chat_id)
        if chat_id_str in self.subscribers:
            return self.subscribers[chat_id_str].get('is_blocked', True)
        return True
    
    def get_subscribers_list(self):
        """Возвращает список chat_id только НЕ ЗАБЛОКИРОВАННЫХ подписчиков"""
        return [
            int(chat_id) for chat_id, data in self.subscribers.items()
            if not data.get('is_blocked', False)
        ]
    
    def get_all_subscribers_list(self):
        """Возвращает список chat_id ВСЕХ подписчиков (включая заблокированных)"""
        return [int(chat_id) for chat_id in self.subscribers.keys()]
    
    def clear_all(self):
        self.subscribers = {}
        self._save()
        logger.info("🗑️ Все подписчики удалены")


# Глобальные экземпляры
signals_history = SignalsHistory()
subscribers_manager = None  # Будет инициализирован в main.py с передачей admin_chat_id