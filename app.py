from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Literal
import psycopg2.pool
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(".env 파일에 DATABASE_URL 설정이 없습니다.")

if "sslmode" not in DATABASE_URL:
    DATABASE_URL += ("?" if "?" not in DATABASE_URL else "&") + "sslmode=require"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_pool = psycopg2.pool.ThreadedConnectionPool(1, 5, DATABASE_URL)

app = FastAPI()


@app.on_event("startup")
def startup():
    conn = _pool.getconn()
    ok = False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS public.kpidb (
                  env        TEXT NOT NULL,
                  key        TEXT NOT NULL,
                  value      TEXT,
                  updated_at TIMESTAMPTZ DEFAULT NOW(),
                  PRIMARY KEY (env, key)
                )
            """)
            cur.execute("ALTER TABLE public.kpidb DISABLE ROW LEVEL SECURITY")
        conn.commit()
        ok = True
        print("[DB] 테이블 준비 완료")
    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print(f"[DB] 자동 초기화 실패 — Supabase 대시보드에서 수동 실행 필요: {e}")
    finally:
        _pool.putconn(conn, close=not ok)


class DataPayload(BaseModel):
    key: str
    value: str


@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"), media_type="text/html; charset=utf-8")


@app.get("/api/data")
def get_data(env: Literal["main", "dev"] = "main"):
    conn = _pool.getconn()
    ok = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT key, value FROM kpidb WHERE env = %s", (env,))
            result = {r[0]: r[1] for r in cur.fetchall()}
        ok = True
        return result
    except Exception:
        raise HTTPException(status_code=500, detail="DB 조회 오류")
    finally:
        _pool.putconn(conn, close=not ok)


@app.post("/api/data")
def set_data(payload: DataPayload, env: Literal["main", "dev"] = "main"):
    conn = _pool.getconn()
    ok = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO kpidb (env, key, value, updated_at) VALUES (%s, %s, %s, NOW()) "
                "ON CONFLICT (env, key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
                (env, payload.key, payload.value),
            )
            conn.commit()
        ok = True
        return {"ok": True}
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="DB 저장 오류")
    finally:
        _pool.putconn(conn, close=not ok)
