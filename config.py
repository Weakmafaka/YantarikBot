import os
from datetime import timedelta

class BaseConfig:
    """Базовая конфигурация"""
    # Основные настройки бота
    MAIN_ADMIN_ID = None
    DATABASE_PATH = "bot_database.db"
    
    # Настройки логирования
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
    
    # Настройки подписки
    TRIAL_DURATION = timedelta(days=7)
    SUBSCRIPTION_PRICES = {
        30: 299,   # 1 месяц
        90: 799,   # 3 месяца
        180: 1499, # 6 месяцев
        365: 2499  # 12 месяцев
    }
    
    # Ограничения
    MAX_AI_REQUESTS_PER_DAY = 50
    MAX_FILE_SIZE_MB = 20
    
    # Таймауты
    REQUEST_TIMEOUT = 30
    LONG_POLLING_TIMEOUT = 60

class DevelopmentConfig(BaseConfig):
    """Конфигурация для разработки"""
    LOG_LEVEL = "DEBUG"
    DATABASE_PATH = "dev_database.db"
    
    # Тестовые настройки
    TEST_USER_ID = 123456789
    ENABLE_DEBUG_COMMANDS = True

class ProductionConfig(BaseConfig):
    """Конфигурация для продакшена"""
    LOG_LEVEL = "INFO"
    LOG_FILE = "bot.log"
    
    # Продакшен настройки
    ENABLE_DEBUG_COMMANDS = False
    BACKUP_DATABASE_PATH = "/backup/bot_database.backup"
    
    # Настройки безопасности
    MAX_LOGIN_ATTEMPTS = 3
    LOGIN_TIMEOUT = 300  # 5 минут

class TestingConfig(BaseConfig):
    """Конфигурация для тестирования"""
    LOG_LEVEL = "DEBUG"
    DATABASE_PATH = ":memory:"  # Используем SQLite в памяти
    TESTING = True

# Выбор конфигурации на основе переменной окружения
def get_config():
    env = os.getenv("BOT_ENV", "development").lower()
    configs = {
        "development": DevelopmentConfig,
        "production": ProductionConfig,
        "testing": TestingConfig
    }
    return configs.get(env, DevelopmentConfig) 