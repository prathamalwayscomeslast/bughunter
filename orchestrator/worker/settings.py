from arq.connections import RedisSettings
from config import REDIS_URL
from worker.tasks import process_bug_job

class WorkerSettings:
    functions = [process_bug_job]
    redis_settings = RedisSettings.from_dsn(REDIS_URL)