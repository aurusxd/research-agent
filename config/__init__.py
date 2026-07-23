from os import environ as env
import os

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from .database import DbConfig

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
class Config(BaseModel):
    database: DbConfig = Field(default_factory=lambda: DbConfig(**env))


config = Config()
