import string
import random
import asyncio
from loguru import logger
from dataclasses import dataclass

USER_DATA_PATH = "bot/user_data/data"

# https://pynative.com/python-generate-random-string/
def generate_random_string(length: int) -> str:
    """Returns random generated string with a certain quantity letters"""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for i in range(length))


async def execute_command(cmd: list):
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        logger.debug(f'[{cmd!r} exited with {proc.returncode}]')
        logger.debug(f'[stdout]\n{stdout.decode()}')
        logger.debug(f'[stderr]\n{stderr.decode()}')
        assert proc.returncode == 0
        return proc


async def process_output_lines(process):
  async for line in process.stdout:
    yield line.rstrip().decode()

@dataclass
class PATH:
    """Возвращяет путь к личным папкам пользывателей, а-ля конструктор путей"""
    user_id: str
    user_folder: str = ""

    def tmp_audio_samples(self, file_name="") -> str:
        return f'{USER_DATA_PATH}/audio_sample/tmp/{self.user_id}/{self.user_folder}/{file_name}'
    def processed_audio_samples(self, file_name="") -> str:
        return f'{USER_DATA_PATH}/audio_sample/processed/{self.user_id}/{self.user_folder}/{file_name}'

    def tmp_query_audio(self, file_name="") -> str:
        return f'{USER_DATA_PATH}/query/tmp/{self.user_id}/{self.user_folder}/{file_name}'
    def processed_query_audio(self, file_name="") -> str:
        return f'{USER_DATA_PATH}/query/processed/{self.user_id}/{self.user_folder}/{file_name}'

    def fingerprint_db(self) -> str:
        return f'{USER_DATA_PATH}/audio_sample/fingerprint_db/{self.user_id}/{self.user_folder}.fpdb'
    def fingerprint_db_dir_path(self) -> str:
        return f'{USER_DATA_PATH}/audio_sample/fingerprint_db/{self.user_id}/'

# TODO: drop
path = PATH
