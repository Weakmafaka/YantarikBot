import sqlite3
import datetime
from typing import Optional, Dict, Any, List
from datetime import date
from utils.logger import get_logger

logger = get_logger(__name__)

class Database:
    def __init__(self, db_file: str = "bot_database.db"):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self._create_tables()
        self._create_indexes()
    
    def _create_indexes(self) -> None:
        """Создание индексов для оптимизации запросов"""
        indexes = [
            # Индексы для таблицы users
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)",
            "CREATE INDEX IF NOT EXISTS idx_users_premium ON users(is_premium)",
            "CREATE INDEX IF NOT EXISTS idx_users_premium_until ON users(premium_until)",
            "CREATE INDEX IF NOT EXISTS idx_users_last_activity ON users(last_activity)",
            
            # Индексы для таблицы payments
            "CREATE INDEX IF NOT EXISTS idx_payments_user_id ON payments(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status)",
            "CREATE INDEX IF NOT EXISTS idx_payments_date ON payments(payment_date)",
            
            # Индексы для таблицы ai_usage
            "CREATE INDEX IF NOT EXISTS idx_ai_usage_date ON ai_usage(usage_date)",
            "CREATE INDEX IF NOT EXISTS idx_ai_usage_user ON ai_usage(user_id, usage_date)",
            
            # Индексы для таблицы gift_subscriptions
            "CREATE INDEX IF NOT EXISTS idx_gift_status ON gift_subscriptions(is_redeemed)",
            "CREATE INDEX IF NOT EXISTS idx_gift_sender ON gift_subscriptions(sender_id)",
            "CREATE INDEX IF NOT EXISTS idx_gift_recipient ON gift_subscriptions(redeemed_by)"
        ]
        
        for index in indexes:
            try:
                self.cursor.execute(index)
                logger.info("index_created", index_query=index)
            except sqlite3.Error as e:
                logger.error("index_creation_failed",
                    index_query=index,
                    error=str(e)
                )
        
        self.connection.commit()

    def _create_tables(self) -> None:
        """Создание необходимых таблиц при инициализации"""
        try:
            # Добавляем COLLATE NOCASE для регистронезависимого поиска по username
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT COLLATE NOCASE,
                first_name TEXT,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_premium BOOLEAN DEFAULT 0,
                premium_until TIMESTAMP,
                payment_method_id TEXT,
                trial_used BOOLEAN DEFAULT 0,
                age_group TEXT,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            ''')
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                permissions_level INTEGER DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')
            self.connection.commit()

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS age_selection_stats (
                    age_group TEXT PRIMARY KEY,
                    selection_count INTEGER DEFAULT 0
                )
                ''')

            for age_group in ["0-3", "4-6", "7-10"]:
                self.cursor.execute(
                    "INSERT OR IGNORE INTO age_selection_stats (age_group, selection_count) VALUES (?, 0)",
                    (age_group,)
                )
            self.connection.commit()

            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS payments (
                payment_id TEXT PRIMARY KEY,
                user_id INTEGER,
                amount REAL,
                currency TEXT,
                status TEXT,
                payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_recurring BOOLEAN DEFAULT 0,
                description TEXT,
                payment_method_id TEXT,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')
            
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_usage (
                user_id INTEGER,
                usage_date DATE,
                count INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, usage_date),
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
            ''')

            # Проверяем, существует ли столбец last_activity
            self.cursor.execute("PRAGMA table_info(users)")
            columns = [column[1] for column in self.cursor.fetchall()]
            if "last_activity" not in columns:
                self.cursor.execute("ALTER TABLE users ADD COLUMN last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    added_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                ''')
            default_admins = [
                (1692506573, "lenamalchevskaya"),
                (768903494, "lisov18"),
                (989687907, "vvv_valeria")
            ]

            for admin_id, username in default_admins:
                self.cursor.execute(
                    "INSERT OR IGNORE INTO admins (user_id, username) VALUES (?, ?)",
                    (admin_id, username)
                )

            self.connection.commit()

            # Таблица для подарочных подписок
            self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS gift_subscriptions (
                gift_code TEXT PRIMARY KEY,
                sender_id INTEGER NOT NULL,
                is_redeemed BOOLEAN DEFAULT 0,
                redeemed_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                redeemed_at TIMESTAMP
            )
            """)
            self.connection.commit()

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS locked_categories (
                    category_name TEXT PRIMARY KEY
                )
                ''')
            self.connection.commit()

            logger.info("tables_created_successfully")
        except sqlite3.Error as e:
            logger.error("table_creation_failed", error=str(e))
            raise

    def add_locked_category(self, category_name: str) -> bool:
        """Добавляет категорию в список закрытых"""
        try:
            self.cursor.execute(
                "INSERT INTO locked_categories (category_name) VALUES (?)",
                (category_name,)
            )
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:  # Категория уже существует
            return False

    def remove_locked_category(self, category_name: str) -> bool:
        """Удаляет категорию из списка закрытых"""
        self.cursor.execute(
            "DELETE FROM locked_categories WHERE category_name = ?",
            (category_name,)
        )
        self.connection.commit()
        return self.cursor.rowcount > 0

    def is_category_locked(self, category_name: str) -> bool:
        """Проверяет, заблокирована ли категория"""
        self.cursor.execute(
            "SELECT 1 FROM locked_categories WHERE category_name = ?",
            (category_name,)
        )
        return bool(self.cursor.fetchone())

    def get_all_locked_categories(self) -> List[str]:
        """Возвращает список всех заблокированных категорий"""
        self.cursor.execute("SELECT category_name FROM locked_categories")
        return [row[0] for row in self.cursor.fetchall()]
    
    def add_user(self, user_id: int, username: str = None, first_name: str = None) -> None:
        """Добавление нового пользователя в базу данных"""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute(
            "INSERT OR IGNORE INTO users (user_id, username, first_name, last_activity) VALUES (?, ?, ?, ?)",
            (user_id, username, first_name, current_time)
        )
        self.connection.commit()

    def increment_age_selection(self, age_group: str) -> None:
        """Увеличивает счетчик выбора возрастной группы"""
        self.cursor.execute(
            "UPDATE age_selection_stats SET selection_count = selection_count + 1 WHERE age_group = ?",
            (age_group,)
        )
        self.connection.commit()

    def get_age_selection_stats(self) -> Dict[str, int]:
        """Получает статистику по выбору возрастных групп"""
        self.cursor.execute("SELECT age_group, selection_count FROM age_selection_stats")
        stats = self.cursor.fetchall()
        return {age_group: count for age_group, count in stats}
    
    def user_exists(self, user_id: int) -> bool:
        """Проверка существования пользователя в базе"""
        self.cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        return bool(self.cursor.fetchone())
    
    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе"""
        try:
            self.cursor.execute(
                """
                SELECT user_id, username, first_name, registration_date, 
                       is_premium, premium_until, payment_method_id, 
                       trial_used, age_group, last_activity
                FROM users 
                WHERE user_id = ?
                """,
                (user_id,)
            )
            user = self.cursor.fetchone()

            if user:
                logger.info("user_found",
                    user_id=user_id,
                    username=user[1]
                )
                return {
                    "user_id": user[0],
                    "username": user[1],
                    "first_name": user[2],
                    "registration_date": user[3],
                    "is_premium": bool(user[4]),
                    "premium_until": user[5],
                    "payment_method_id": user[6],
                    "trial_used": bool(user[7]),
                    "age_group": user[8],
                    "last_activity": user[9]
                }
            
            logger.warning("user_not_found",
                user_id=user_id
            )
            return None

        except sqlite3.Error as e:
            logger.error("user_fetch_failed",
                user_id=user_id,
                error=str(e)
            )
            raise

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Получение информации о пользователе по никнейму"""
        try:
            # Используем подготовленный запрос и COLLATE NOCASE
            self.cursor.execute(
                """
                SELECT user_id, username, first_name, is_premium, premium_until,
                       payment_method_id, trial_used, age_group, last_activity
                FROM users 
                WHERE username = ? COLLATE NOCASE
                """,
                (username,)
            )
            user = self.cursor.fetchone()
            
            if user:
                logger.info("user_found_by_username",
                    username=username,
                    user_id=user[0]
                )
                return {
                    "user_id": user[0],
                    "username": user[1],
                    "first_name": user[2],
                    "is_premium": bool(user[3]),
                    "premium_until": user[4],
                    "payment_method_id": user[5],
                    "trial_used": bool(user[6]),
                    "age_group": user[7],
                    "last_activity": user[8]
                }
            
            logger.warning("user_not_found_by_username",
                username=username
            )
            return None
            
        except sqlite3.Error as e:
            logger.error("user_fetch_by_username_failed",
                username=username,
                error=str(e)
            )
            raise
    
    def set_premium_status(self, user_id: int, is_premium: bool, days: int = 0) -> None:
        """Установка премиум статуса для пользователя"""
        if days > 0:
            premium_until = (datetime.datetime.now() + datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        else:
            premium_until = None
        self.cursor.execute(
            "UPDATE users SET is_premium = ?, premium_until = ? WHERE user_id = ?",
            (is_premium, premium_until, user_id)
        )
        self.connection.commit()
    
    def set_trial_used(self, user_id: int, trial_used: bool = True) -> None:
        """Отметка об использовании триального периода"""
        self.cursor.execute(
            "UPDATE users SET trial_used = ? WHERE user_id = ?",
            (trial_used, user_id)
        )
        self.connection.commit()
    
    def save_payment_method(self, user_id: int, payment_method_id: str) -> None:
        """Сохранение метода оплаты пользователя"""
        self.cursor.execute(
            "UPDATE users SET payment_method_id = ? WHERE user_id = ?",
            (payment_method_id, user_id)
        )
        self.connection.commit()
    
    def add_payment(self, payment_id: str, user_id: int, amount: float, currency: str, 
                    status: str, is_recurring: bool = False, description: str = "", 
                    payment_method_id: str = None) -> None:
        """Добавление записи о платеже"""
        self.cursor.execute(
            "INSERT INTO payments (payment_id, user_id, amount, currency, status, "
            "is_recurring, description, payment_method_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (payment_id, user_id, amount, currency, status, is_recurring, description, payment_method_id)
        )
        self.connection.commit()
    
    def update_payment_status(self, payment_id: str, status: str) -> None:
        """Обновление статуса платежа"""
        self.cursor.execute(
            "UPDATE payments SET status = ? WHERE payment_id = ?",
            (status, payment_id)
        )
        self.connection.commit()
    
    def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Получение информации о платеже"""
        self.cursor.execute(
            "SELECT payment_id, user_id, amount, currency, status, payment_date, "
            "is_recurring, description, payment_method_id FROM payments WHERE payment_id = ?",
            (payment_id,)
        )
        payment = self.cursor.fetchone()
        
        if not payment:
            return None
            
        return {
            "payment_id": payment[0],
            "user_id": payment[1],
            "amount": payment[2],
            "currency": payment[3],
            "status": payment[4],
            "payment_date": payment[5],
            "is_recurring": bool(payment[6]),
            "description": payment[7],
            "payment_method_id": payment[8]
        }
    
    def check_premium_status(self, user_id: int) -> bool:
        """Проверка премиум статуса пользователя"""
        self.cursor.execute(
            "SELECT is_premium, premium_until FROM users WHERE user_id = ?",
            (user_id,)
        )
        user = self.cursor.fetchone()
        
        if not user or not user[0]:
            return False
            
        # Если премиум статус активен, проверяем не истек ли срок
        if user[1]:
            premium_until = datetime.datetime.strptime(user[1], "%Y-%m-%d %H:%M:%S")
            if premium_until < datetime.datetime.now():
                # Срок истек - обновляем статус
                self.set_premium_status(user_id, False)
                return False
                
        return bool(user[0])
    
    def get_users_for_recurring_payment(self) -> List[Dict[str, Any]]:
        """Получение списка пользователей для рекуррентного платежа"""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        self.cursor.execute(
            "SELECT user_id, payment_method_id FROM users "
            "WHERE is_premium = 1 AND premium_until <= ? AND payment_method_id IS NOT NULL",
            (current_time,)
        )
        
        users = self.cursor.fetchall()
        return [{"user_id": user[0], "payment_method_id": user[1]} for user in users]
    
    def set_user_age(self, user_id: int, age_group: str) -> None:
        """Установка возрастной группы пользователя"""
        self.cursor.execute(
            "UPDATE users SET age_group = ? WHERE user_id = ?",
            (age_group, user_id)
        )
        self.connection.commit()
    
    def get_user_age(self, user_id: int) -> Optional[str]:
        """Получение возрастной группы пользователя"""
        self.cursor.execute(
            "SELECT age_group FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = self.cursor.fetchone()
        return result[0] if result and result[0] else None
    
    def is_subscribed(self, user_id: int) -> bool:
        """Проверяет, активна ли подписка пользователя (синоним check_premium_status)."""
        return self.check_premium_status(user_id)
    
    def get_ai_usage(self, user_id: int, usage_date: date) -> int:
        """Получает количество использований AI пользователем за указанную дату."""
        self.cursor.execute(
            "SELECT count FROM ai_usage WHERE user_id = ? AND usage_date = ?",
            (user_id, usage_date.strftime('%Y-%m-%d'))
        )
        result = self.cursor.fetchone()
        return result[0] if result else 0
    
    def increment_ai_usage(self, user_id: int, usage_date: date) -> None:
        """Увеличивает счетчик использования AI пользователем за указанную дату."""
        date_str = usage_date.strftime('%Y-%m-%d')
        self.cursor.execute(
            "INSERT INTO ai_usage (user_id, usage_date, count) "
            "VALUES (?, ?, 1) "
            "ON CONFLICT(user_id, usage_date) DO UPDATE SET count = count + 1;",
            (user_id, date_str)
        )
        self.connection.commit()
    
    def update_user_activity(self, user_id: int) -> None:
        """Обновляет время последней активности пользователя."""
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute(
            "UPDATE users SET last_activity = ? WHERE user_id = ?",
            (current_time, user_id)
        )
        self.connection.commit()
    
    def get_inactive_users(self, days: int = 2) -> List[Dict[str, Any]]:
        """Получает список пользователей, неактивных более указанного количества дней."""
        cutoff_date = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
        
        self.cursor.execute(
            "SELECT user_id, username, first_name, last_activity, age_group FROM users "
            "WHERE last_activity < ?",
            (cutoff_date,)
        )
        
        users = self.cursor.fetchall()
        return [
            {
                "user_id": user[0],
                "username": user[1],
                "first_name": user[2],
                "last_activity": user[3],
                "age_group": user[4]
            } 
            for user in users
        ]
    
    def close(self) -> None:
        """Закрытие соединения с базой данных"""
        self.connection.close()

    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Возвращает список пользователей с пагинацией"""
        try:
            self.cursor.execute(
                "SELECT * FROM users ORDER BY registration_date DESC LIMIT ? OFFSET ?",
                (limit, offset)
            )
            rows = self.cursor.fetchall()
            columns = [desc[0] for desc in self.cursor.description]
            users = [dict(zip(columns, row)) for row in rows]
            
            logger.info("users_fetched",
                limit=limit,
                offset=offset,
                count=len(users)
            )
            return users
        except sqlite3.Error as e:
            logger.error("users_fetch_failed",
                limit=limit,
                offset=offset,
                error=str(e)
            )
            raise

    def delete_user(self, user_id: int) -> None:
        """Удаляет пользователя из базы данных по user_id и все связанные записи"""
        self.cursor.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
        self.cursor.execute("DELETE FROM ai_usage WHERE user_id = ?", (user_id,))
        self.cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

        self.connection.commit()

    def add_admin(self, user_id: int, username: str = None) -> None:
        """Добавление администратора в базу данных"""
        self.cursor.execute(
            "INSERT OR REPLACE INTO admins (user_id, username) VALUES (?, ?)",
            (user_id, username)
        )
        self.connection.commit()

    def remove_admin(self, user_id: int) -> None:
        """Удаление администратора из базы данных"""
        self.cursor.execute(
            "DELETE FROM admins WHERE user_id = ?",
            (user_id,)
        )
        self.connection.commit()

    def get_admin(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение информации об администраторе"""
        self.cursor.execute(
            "SELECT user_id, username, added_date FROM admins WHERE user_id = ?",
            (user_id,)
        )
        admin = self.cursor.fetchone()

        if not admin:
            return None

        return {
            "user_id": admin[0],
            "username": admin[1],
            "added_date": admin[2]
        }

    def is_admin(self, user_id: int) -> bool:
        """Проверка, является ли пользователь администратором"""
        return bool(self.get_admin(user_id))

    def get_all_admins(self) -> List[Dict[str, Any]]:
        """Получение списка всех администраторов"""
        self.cursor.execute(
            "SELECT user_id, username, added_date FROM admins"
        )
        admins = self.cursor.fetchall()
        return [
            {
                "user_id": admin[0],
                "username": admin[1],
                "added_date": admin[2]
            }
            for admin in admins
        ]

    def add_gift_subscription(self, gift_code: str, sender_id: int) -> None:
        """Создание записи о подарочной подписке"""
        self.cursor.execute(
            "INSERT OR IGNORE INTO gift_subscriptions (gift_code, sender_id) VALUES (?, ?)",
            (gift_code, sender_id)
        )
        self.connection.commit()
    
    def redeem_gift_subscription(self, gift_code: str, recipient_id: int) -> bool:
        """Активировать подарочную подписку по коду"""
        # Проверяем запись
        self.cursor.execute(
            "SELECT sender_id, is_redeemed FROM gift_subscriptions WHERE gift_code = ?",
            (gift_code,)
        )
        row = self.cursor.fetchone()
        if not row or row[1]:
            return False
        sender_id = row[0]
        # Нельзя активировать у себя
        if sender_id == recipient_id:
            return False
        # Активируем подарок
        redeemed_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute(
            "UPDATE gift_subscriptions SET is_redeemed = 1, redeemed_by = ?, redeemed_at = ? WHERE gift_code = ?",
            (recipient_id, redeemed_at, gift_code)
        )
        self.connection.commit()
        return True

# Экземпляр базы данных по умолчанию
db = Database()