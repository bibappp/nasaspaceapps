"""Агро-Севооборот: API бэкенда."""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.accounts import router as accounts_router
from .api.routes import router
from .config import get_settings
from .db import init_db
from .model.rules import get_rules

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_rules()  # правила проверяются при запуске: ошибка в YAML не даст серверу стартовать
    get_settings().cache_dir.mkdir(parents=True, exist_ok=True)
    init_db()
    from .services.fields import cleanup_demo_users

    cleanup_demo_users(get_settings().demo_ttl_days)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Агро-Севооборот API",
    description="Инструмент поддержки решений по севообороту для Северного Казахстана. "
    "Окончательное решение принимает фермер.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-Requested-With"],
    allow_credentials=True,
)
app.include_router(router)
app.include_router(accounts_router)

