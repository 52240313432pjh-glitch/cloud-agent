import asyncio
import os
from pathlib import Path

from fastapi import APIRouter
from dotenv import load_dotenv

router = APIRouter()

ENV_FILE = Path(__file__).resolve().parents[2] / "agent" / ".env"
load_dotenv(ENV_FILE)


@router.get("/users")
async def list_users():
    """Return distinct user ids found in the business database."""
    try:
        users = await asyncio.wait_for(asyncio.to_thread(_query_users_from_mysql), timeout=3)
        return {"users": users}
    except Exception as exc:
        return {"users": [], "error": str(exc)}


def _query_users_from_mysql():
    import pymysql

    connection = pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", 3306)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "mydb"),
        cursorclass=pymysql.cursors.DictCursor,
        connect_timeout=2,
        read_timeout=2,
        write_timeout=2,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id FROM cloud_orders
                UNION
                SELECT user_id FROM cloud_instances
                UNION
                SELECT user_id FROM instance_metrics_daily
                ORDER BY user_id
                """
            )
            rows = cursor.fetchall()
    finally:
        connection.close()

    return [
        {
            "id": row["user_id"],
            "label": row["user_id"],
        }
        for row in rows
        if row.get("user_id")
    ]
