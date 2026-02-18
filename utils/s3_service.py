import boto3
from aiogram.types import InlineKeyboardButton
from botocore.exceptions import ClientError
import logging
from concurrent.futures import ThreadPoolExecutor
import asyncio
from typing import List, Tuple, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
import time
from prometheus_client import start_http_server, Counter, Histogram
import os

# ==================== Конфигурация ====================
S3_CONFIG = {
    'endpoint_url': os.getenv('S3_ENDPOINT'),
    'aws_access_key_id': os.getenv('S3_ACCESS_KEY'),
    'aws_secret_access_key': os.getenv('S3_SECRET_KEY'),
    'region_name': os.getenv('S3_REGION')
}
S3_BUCKET_NAME = os.getenv('S3_BUCKET')
S3_PUBLIC_BASE_URL = os.getenv('S3_PUBLIC_URL')

# ==================== Инициализация ====================
s3_client = boto3.client('s3', **S3_CONFIG)
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 50))
executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)

# ==================== Ограничители ====================
# Для разных типов операций S3
S3_LIST_SEMAPHORE = asyncio.Semaphore(int(os.getenv('S3_LIST_LIMIT', 30)))
S3_GET_SEMAPHORE = asyncio.Semaphore(int(os.getenv('S3_GET_LIMIT', 50)))

# Для Telegram API
TG_API_SEMAPHORE = asyncio.Semaphore(int(os.getenv('TG_API_LIMIT', 10)))

# Для ограничения по пользователям
USER_SEMAPHORES = {}
USER_LIMIT = int(os.getenv('USER_LIMIT', 3))

# ==================== Мониторинг ====================
# Метрики Prometheus
REQUESTS_TOTAL = Counter('requests_total', 'Total requests')
S3_REQUESTS = Counter('s3_requests_total', 'S3 requests by type', ['operation'])
S3_LATENCY = Histogram('s3_latency_seconds', 'S3 request latency', ['operation'])
TG_REQUESTS = Counter('tg_requests_total', 'Telegram API requests')
TG_LATENCY = Histogram('tg_latency_seconds', 'Telegram API latency')
ERRORS = Counter('errors_total', 'Total errors', ['type'])

# Запуск сервера метрик
start_http_server(8000)

# ==================== Вспомогательные функции ====================
def get_user_semaphore(user_id: int) -> asyncio.Semaphore:
    """Получаем семафор для конкретного пользователя"""
    if user_id not in USER_SEMAPHORES:
        USER_SEMAPHORES[user_id] = asyncio.Semaphore(USER_LIMIT)
    return USER_SEMAPHORES[user_id]

async def safe_telegram_request(func, *args, **kwargs):
    """Безопасный вызов Telegram API с ограничением скорости"""
    start_time = time.time()
    async with TG_API_SEMAPHORE:
        try:
            result = await func(*args, **kwargs)
            TG_REQUESTS.inc()
            TG_LATENCY.observe(time.time() - start_time)
            return result
        except Exception as e:
            ERRORS.labels(type='telegram').inc()
            logging.error(f"Telegram API error: {e}")
            raise

# ==================== Основные функции S3 ====================
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
def list_objects_sync(prefix: str) -> List[Dict]:
    """Синхронный список объектов с повторными попытками"""
    start_time = time.time()
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        result = list(paginator.paginate(Bucket=S3_BUCKET_NAME, Prefix=prefix, Delimiter="/"))
        S3_REQUESTS.labels(operation='list').inc()
        S3_LATENCY.labels(operation='list').observe(time.time() - start_time)
        return result
    except Exception as e:
        ERRORS.labels(type='s3_list').inc()
        raise

async def list_s3_objects(prefix: str) -> List[Dict]:
    """Асинхронная обертка для list_objects"""
    async with S3_LIST_SEMAPHORE:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, list_objects_sync, prefix)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
def list_objects_simple_sync(prefix: str) -> Dict:
    """Синхронная версия list_objects_v2 без пагинации"""
    start_time = time.time()
    try:
        result = s3_client.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=prefix,
            Delimiter='/'
        )
        S3_REQUESTS.labels(operation='list_simple').inc()
        S3_LATENCY.labels(operation='list_simple').observe(time.time() - start_time)
        return result
    except Exception as e:
        ERRORS.labels(type='s3_list_simple').inc()
        raise

async def list_objects_simple(prefix: str) -> Dict:
    """Асинхронная версия list_objects_simple"""
    async with S3_LIST_SEMAPHORE:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, list_objects_simple_sync, prefix)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
def generate_presigned_url_sync(key: str) -> str:
    """Синхронная генерация URL с повторными попытками"""
    start_time = time.time()
    try:
        result = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_BUCKET_NAME,
                'Key': key,
                'ResponseContentDisposition': f'attachment; filename="{key.split("/")[-1]}"',
                'ResponseContentType': 'application/octet-stream'
            },
            ExpiresIn=3600
        )
        S3_REQUESTS.labels(operation='presign').inc()
        S3_LATENCY.labels(operation='presign').observe(time.time() - start_time)
        return result
    except Exception as e:
        ERRORS.labels(type='s3_presign').inc()
        raise

async def generate_presigned_url(key: str) -> str:
    """Асинхронная генерация URL"""
    async with S3_GET_SEMAPHORE:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, generate_presigned_url_sync, key)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
def generate_download_url_sync(key: str) -> str:
    """Генерация URL для скачивания с заголовком Content-Disposition"""
    start_time = time.time()
    try:
        result = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': S3_BUCKET_NAME,
                'Key': key,
                'ResponseContentDisposition': f'attachment; filename="{key.split("/")[-1]}"'
            },
            ExpiresIn=3600
        )
        S3_REQUESTS.labels(operation='download_url').inc()
        S3_LATENCY.labels(operation='download_url').observe(time.time() - start_time)
        return result
    except Exception as e:
        ERRORS.labels(type='s3_download_url').inc()
        raise

async def generate_download_url(key: str) -> str:
    """Асинхронная генерация URL для скачивания"""
    async with S3_GET_SEMAPHORE:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(executor, generate_download_url_sync, key)

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
def get_folder_contents_sync(prefix: str) -> List[Dict]:
    """Синхронная версия получения содержимого папки"""
    start_time = time.time()
    try:
        response = s3_client.list_objects_v2(
            Bucket=S3_BUCKET_NAME,
            Prefix=prefix
        )
        S3_REQUESTS.labels(operation='list_contents').inc()
        S3_LATENCY.labels(operation='list_contents').observe(time.time() - start_time)
        return response.get('Contents', [])
    except Exception as e:
        ERRORS.labels(type='s3_list_contents').inc()
        raise

async def get_folder_contents(folder_path: str) -> List[Dict]:
    """Асинхронная версия получения содержимого папки"""
    async with S3_LIST_SEMAPHORE:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            executor,
            get_folder_contents_sync,
            folder_path.rstrip('/') + '/'
        )

# ==================== Основные функции бота ====================
async def get_files_useful(folder: str, type_age: str, callback_prefix: str) -> Tuple[
    List[InlineKeyboardButton], List[str]]:
    """Оптимизированное получение файлов"""
    REQUESTS_TOTAL.inc()
    try:
        prefix = folder.lstrip("/") + "/"
        pages = await list_s3_objects(prefix)

        buttons = []
        item_names = []

        for page in pages:
            # Обработка папок
            common_prefixes = page.get('CommonPrefixes', [])
            buttons.extend(
                InlineKeyboardButton(
                    text=cp["Prefix"].split("/")[-2],
                    callback_data=f"{callback_prefix}{len(item_names) + i}_{type_age}"
                )
                for i, cp in enumerate(common_prefixes)
            )
            item_names.extend(cp["Prefix"].split("/")[-2] for cp in common_prefixes)

            # Обработка файлов
            contents = [obj for obj in page.get("Contents", []) if obj["Key"].split("/")[-1]]
            buttons.extend(
                InlineKeyboardButton(
                    text=obj["Key"].split("/")[-1],
                    callback_data=f"{callback_prefix}{len(item_names) + i}_{type_age}"
                )
                for i, obj in enumerate(contents)
            )
            item_names.extend(obj["Key"].split("/")[-1] for obj in contents)

        return buttons, item_names
    except Exception as e:
        ERRORS.labels(type='get_files').inc()
        logging.error(f"S3 error: {e}", exc_info=True)
        return [], []

async def get_files(folder: str, type_age: str, callback: str) -> Tuple[List[Dict[str, str]], List[str]]:
    """Альтернативная версия get_files_useful с другим форматом вывода"""
    REQUESTS_TOTAL.inc()
    try:
        response = await list_objects_simple(folder.rstrip('/') + '/')

        buttons = []
        item_names = []

        # Обработка папок
        if 'CommonPrefixes' in response:
            buttons.extend({
                'text': prefix['Prefix'].split('/')[-2],
                'callback_data': f"{callback}{i}_{type_age}"
            } for i, prefix in enumerate(response['CommonPrefixes']))

            item_names.extend(
                prefix['Prefix'].split('/')[-2]
                for prefix in response['CommonPrefixes']
            )

        # Обработка файлов
        if 'Contents' in response:
            start_idx = len(item_names)
            buttons.extend({
                'text': obj['Key'].split('/')[-1],
                'callback_data': f"{callback}{start_idx + i}_{type_age}"
            } for i, obj in enumerate(
                obj for obj in response['Contents']
                if not obj['Key'].endswith('/')
            ))

            item_names.extend(
                obj['Key'].split('/')[-1]
                for obj in response['Contents']
                if not obj['Key'].endswith('/')
            )

        return buttons, item_names
    except ClientError as e:
        ERRORS.labels(type='get_files_alt').inc()
        logging.error(f"S3 list error for {folder}: {e}", exc_info=True)
        return [], []

async def get_url(prefix: str) -> List[Any]:
    """Оптимизированное получение URL с батчингом"""
    REQUESTS_TOTAL.inc()
    try:
        prefix = prefix.lstrip("/") + "/"
        pages = await list_s3_objects(prefix)

        result = []
        for page in pages:
            # Обработка папок
            result.extend(
                type('Obj', (object,), {
                    "type": "dir",
                    "name": cp['Prefix'].rstrip('/').split('/')[-1],
                    "file": None
                })
                for cp in page.get('CommonPrefixes', [])
            )

            # Параллельная обработка файлов батчами
            file_objects = [obj for obj in page.get("Contents", []) if not obj["Key"].endswith('/')]

            batch_size = 20
            for i in range(0, len(file_objects), batch_size):
                batch = file_objects[i:i + batch_size]
                tasks = [generate_presigned_url(obj["Key"]) for obj in batch]
                urls = await asyncio.gather(*tasks, return_exceptions=True)

                for obj, url in zip(batch, urls):
                    if not isinstance(url, Exception):
                        result.append(type('Obj', (object,), {
                            "type": "file",
                            "name": obj["Key"].split("/")[-1],
                            "file": url
                        }))

        return result
    except Exception as e:
        ERRORS.labels(type='get_url').inc()
        logging.error(f"S3 URL error: {e}", exc_info=True)
        return []
