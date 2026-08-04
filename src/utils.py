import json
import logging
from datetime import datetime
from pathlib import Path

def setup_logging():
    """Настройка логирования с правильной кодировкой"""
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    log_file = log_dir / f'bot_{datetime.now().strftime("%Y%m%d")}.log'
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),  # ← ДОБАВЛЕНО encoding='utf-8'
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)