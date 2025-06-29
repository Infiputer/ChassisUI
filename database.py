import asyncpg
from fastapi import FastAPI, Request
from config import DATABASE_URL

async def get_db_pool(request: Request):
    return request.app.state.db_pool

async def startup(app: FastAPI):
    app.state.db_pool = await asyncpg.create_pool(DATABASE_URL)

async def shutdown(app: FastAPI):
    await app.state.db_pool.close()

