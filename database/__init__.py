import logging
import sqlite3
import os
from pathlib import Path
from config import config

logger = logging.getLogger('doc_bot.database')
logger.info("database/__init__.py ЗАГРУЖЕН УСПЕШНО")


def init_db():
    """Инициализирует базу данных, создавая необходимые таблицы"""
    try:
        # Создаем директорию для базы данных, если она не существует
        db_path = Path(config.DATABASE_PATH)
        db_path.parent.mkdir(parents=True, exist_ok=True)

        # Подключаемся к базе данных
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Создаем таблицу пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            language_code TEXT,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            referrer_id INTEGER,
            partner_points REAL DEFAULT 0.0,
            is_subscribed BOOLEAN DEFAULT 1
        )
        ''')

        # Создаем таблицу шаблонов документов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            description TEXT,
            template_name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Создаем таблицу заказов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_price REAL NOT NULL,
            item_count INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'created', -- Базовый статус при создании заказа
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            savings REAL DEFAULT 0.0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')

        # Создаем таблицу элементов заказа
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            doc_id INTEGER NOT NULL,
            doc_name TEXT NOT NULL,
            price REAL NOT NULL,
            filled_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (doc_id) REFERENCES templates (id)
        )
        ''')

        # Создаем таблицу корзины
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS cart (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            doc_id INTEGER NOT NULL,
            quantity INTEGER DEFAULT 1,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (doc_id) REFERENCES templates (id)
        )
        ''')

        # Создаем таблицу платежей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_system TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payment_id TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )
        ''')

        # Создаем таблицу черновиков
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS drafts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            template_id INTEGER NOT NULL,
            document_name TEXT NOT NULL,
            answers TEXT NOT NULL,
            current_index INTEGER NOT NULL,
            total_questions INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (template_id) REFERENCES templates (id)
        )
        ''')

        # Создаем таблицу промокодов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT NOT NULL UNIQUE,
            discount INTEGER NOT NULL CHECK (discount >= 0 AND discount <= 100),
            max_uses INTEGER NOT NULL DEFAULT 1,
            used_count INTEGER NOT NULL DEFAULT 0,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Создаем таблицу использования промокодов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS promocode_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            promocode_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            order_id INTEGER NOT NULL,
            used_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (promocode_id) REFERENCES promocodes (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )
        ''')

        # Создаем таблицу партнерских баллов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS partner_points (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            points REAL NOT NULL,
            order_id INTEGER,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (order_id) REFERENCES orders (id)
        )
        ''')

        # Создаем таблицу подписчиков новостей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS news_subscribers (
            user_id INTEGER PRIMARY KEY,
            subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')

        # Создаем таблицу поддержки
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS support_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            message TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'new',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')

        # Создаем таблицу сохраненных шаблонов пользователей
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            document_type TEXT NOT NULL,
            data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')

        # Создаем таблицу рефералов
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referrer_id INTEGER NOT NULL,
            referred_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(referrer_id, referred_id)
        )
        ''')

        # Создаем таблицу для хранения цен на услуги (шаблон/автоген)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                service_type TEXT PRIMARY KEY NOT NULL, -- 'template' или 'autogen'
                price INTEGER NOT NULL                    -- Цена в копейках или минимальных единицах
            )
        """)
        logger.info("Таблица prices создана или уже существует")
        # Заполняем значениями по умолчанию, если таблица новая
        cursor.execute("""
            INSERT OR IGNORE INTO prices (service_type, price) VALUES ('template', 19.0)
        """)
        cursor.execute("""
            INSERT OR IGNORE INTO prices (service_type, price) VALUES ('autogen', 249.0)
        """)

        # Сохраняем изменения и закрываем соединение
        conn.commit()
        conn.close()

        logger.info("База данных успешно инициализирована и заполнена тестовыми данными")
        return True

    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}", exc_info=True)
        return False


# Импортируем функции из модулей
from .users import *
from .templates import *
from .orders import *
from .cart import *
from .payments import *
from .drafts import *
from .promocodes import *