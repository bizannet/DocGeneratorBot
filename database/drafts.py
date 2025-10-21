import logging
import sqlite3
import json
from datetime import datetime, timedelta
from config import config

logger = logging.getLogger('doc_bot.drafts')
logger.info("database/drafts.py ЗАГРУЖЕН УСПЕШНО")

def save_draft(user_id: int, template_id: int, document_name: str, answers: dict, current_index: int,
               total_questions: int, category: str = None, doc_info: dict = None) -> int:
    """
    Сохраняет временный черновик заполнения документа (с истечением срока).
    """
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        expires_at = datetime.now() + timedelta(hours=config.DRAFT_EXPIRATION_HOURS)
        expires_at_str = expires_at.strftime("%Y-%m-%d %H:%M:%S")

        # Используем str(answers) как раньше (для совместимости)
        answers_str = str(answers)

        cursor.execute("""
            INSERT INTO drafts (
                user_id, template_id, document_name, answers, 
                current_index, total_questions, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, template_id, document_name, answers_str,
              current_index, total_questions, expires_at_str))

        conn.commit()
        return cursor.lastrowid

    except Exception as e:
        logger.error(f"Ошибка при сохранении временного черновика: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def get_user_drafts(user_id: int) -> list:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("""
            SELECT * FROM drafts 
            WHERE user_id = ? AND expires_at > ?
            ORDER BY created_at DESC
        """, (user_id, current_time))

        drafts = cursor.fetchall()
        drafts_list = []
        for draft in drafts:
            try:
                answers = eval(draft[4])
            except:
                answers = {}
            drafts_list.append({
                'id': draft[0],
                'user_id': draft[1],
                'template_id': draft[2],
                'document_name': draft[3],
                'answers': answers,
                'current_index': draft[5],
                'total_questions': draft[6],
                'created_at': draft[7],
                'expires_at': draft[8]
            })

        return drafts_list

    except Exception as e:
        logger.error(f"Ошибка при получении черновиков пользователя: {e}", exc_info=True)
        return []
    finally:
        if conn:
            conn.close()


def get_draft(user_id: int, draft_id: int = None, template_id: int = None) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        query = "SELECT * FROM drafts WHERE user_id = ?"
        params = [user_id]

        if draft_id:
            query += " AND id = ?"
            params.append(draft_id)
        elif template_id:
            query += " AND template_id = ?"
            params.append(template_id)

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        query += " AND expires_at > ?"
        params.append(current_time)

        cursor.execute(query, tuple(params))
        draft = cursor.fetchone()

        if not draft:
            return None

        try:
            answers = eval(draft[4])
        except:
            answers = {}

        return {
            'id': draft[0],
            'user_id': draft[1],
            'template_id': draft[2],
            'document_name': draft[3],
            'answers': answers,
            'current_index': draft[5],
            'total_questions': draft[6],
            'created_at': draft[7],
            'expires_at': draft[8]
        }

    except Exception as e:
        logger.error(f"Ошибка при получении черновика: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def delete_draft(user_id: int, draft_id: int = None, template_id: int = None) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        query = "DELETE FROM drafts WHERE user_id = ?"
        params = [user_id]

        if draft_id:
            query += " AND id = ?"
            params.append(draft_id)
        elif template_id:
            query += " AND template_id = ?"
            params.append(template_id)

        cursor.execute(query, tuple(params))
        conn.commit()
        return cursor.rowcount > 0

    except Exception as e:
        logger.error(f"Ошибка при удалении черновика: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def clear_expired_drafts() -> int:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute("DELETE FROM drafts WHERE expires_at <= ?", (current_time,))
        conn.commit()
        return cursor.rowcount

    except Exception as e:
        logger.error(f"Ошибка при очистке просроченных черновиков: {e}", exc_info=True)
        return 0
    finally:
        if conn:
            conn.close()

def init_last_drafts_table():
    """Создаёт таблицу для хранения последних черновиков по шаблону."""
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS last_template_drafts (
                user_id INTEGER NOT NULL,
                template_id TEXT NOT NULL,          -- Например: "rental_contract_2025"
                data TEXT NOT NULL,                 -- JSON-строка
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, template_id)
            )
        ''')
        conn.commit()
        logger.info("Таблица last_template_drafts инициализирована")
    except Exception as e:
        logger.error(f"Ошибка при создании таблицы last_template_drafts: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()


def save_last_template_draft(user_id: int, template_id: str, answers: dict) -> bool:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()
        data_str = json.dumps(answers, ensure_ascii=False)

        cursor.execute('''
            INSERT OR REPLACE INTO last_template_drafts (user_id, template_id, data, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, template_id, data_str))

        conn.commit()
        return True

    except Exception as e:
        logger.error(f"Ошибка при сохранении last_template_draft: {e}", exc_info=True)
        return False
    finally:
        if conn:
            conn.close()


def get_last_template_draft(user_id: int, template_id: str) -> dict:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT data FROM last_template_drafts
            WHERE user_id = ? AND template_id = ?
        ''', (user_id, template_id))

        row = cursor.fetchone()
        if not row:
            return None

        return json.loads(row[0])

    except Exception as e:
        logger.error(f"Ошибка при получении last_template_draft: {e}", exc_info=True)
        return None
    finally:
        if conn:
            conn.close()


def clear_last_drafts(user_id: int = None, template_id: str = None) -> int:
    try:
        conn = sqlite3.connect(config.DATABASE_PATH)
        cursor = conn.cursor()

        if user_id is not None and template_id is not None:
            cursor.execute("DELETE FROM last_template_drafts WHERE user_id = ? AND template_id = ?",
                           (user_id, template_id))
        elif user_id is not None:
            cursor.execute("DELETE FROM last_template_drafts WHERE user_id = ?", (user_id,))
        elif template_id is not None:
            cursor.execute("DELETE FROM last_template_drafts WHERE template_id = ?", (template_id,))
        else:
            cursor.execute("DELETE FROM last_template_drafts")

        conn.commit()
        return cursor.rowcount

    except Exception as e:
        logger.error(f"Ошибка при очистке last_template_drafts: {e}", exc_info=True)
        return 0
    finally:
        if conn:
            conn.close()

init_last_drafts_table()