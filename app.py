from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Literal
import psycopg2.pool
import os
import threading
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(".env 파일에 DATABASE_URL 설정이 없습니다.")

# sslmode 외에, 연결 시도가 매달리지 않게 connect_timeout, 끊긴 소켓을 빨리 알아채게 keepalive 를 붙인다
for _k, _v in (("sslmode", "require"), ("connect_timeout", "8"), ("keepalives", "1"),
               ("keepalives_idle", "30"), ("keepalives_interval", "10"), ("keepalives_count", "3")):
    if _k + "=" not in DATABASE_URL:
        DATABASE_URL += ("?" if "?" not in DATABASE_URL else "&") + "%s=%s" % (_k, _v)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Supabase 세션 풀러는 DB 계정당 동시 접속을 5 개로 막는다. 그런데 이 계정은
# 스프링 재고관리(spring-planner)와 같이 쓴다. 예전엔 이 앱이 5 까지, 스프링이 8 까지 열고
# 연결을 쥐고 있어서 한쪽이 자리를 다 차지하면 다른 쪽이 503 으로 멈췄다 (2026-10-06 장애).
# 예산: 스프링 3 + 이 앱 1 = 4. 사용량이 적은 입력 위주 앱이라 1 로 충분하다.
# 연결 1 개는 "동시 사용자 1 명" 이 아니다 — 요청마다 수 ms 빌렸다 돌려준다.
POOL_MAX = 1
_pool = psycopg2.pool.ThreadedConnectionPool(1, POOL_MAX, DATABASE_URL)
# 풀은 비어 있으면 기다리지 않고 바로 PoolError 를 낸다. 상한이 1 이면 동시 요청 두 개 중
# 하나가 그대로 실패하므로, 차례를 기다리게 한다.
_slots = threading.Semaphore(POOL_MAX)
_WAIT_SEC = 10


def _get():
    if not _slots.acquire(timeout=_WAIT_SEC):
        raise HTTPException(status_code=503, detail="서버가 혼잡합니다. 잠시 후 다시 시도해 주세요.")
    try:
        conn = _pool.getconn()
        # 오래 쉰 연결은 풀러가 조용히 끊어 둔다. 그걸 그대로 쓰면 첫 요청이 실패한다.
        try:
            if conn.closed:
                raise psycopg2.OperationalError("닫힌 커넥션")
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            conn.rollback()
        except Exception:
            _pool.putconn(conn, close=True)
            conn = _pool.getconn()
        return conn
    except Exception as e:
        _slots.release()
        print("[DB] 연결 획득 실패: %s" % str(e).strip()[:300], flush=True)
        raise HTTPException(status_code=503, detail="DB 연결을 얻지 못했습니다. 잠시 후 다시 시도해 주세요.")


def _put(conn, close=False):
    try:
        _pool.putconn(conn, close=close)
    finally:
        _slots.release()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://josangwony.github.io"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    conn = _get()
    ok = False
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS kpidb (
                  env        TEXT NOT NULL,
                  key        TEXT NOT NULL,
                  value      TEXT,
                  updated_at TIMESTAMPTZ DEFAULT NOW(),
                  PRIMARY KEY (env, key)
                )
            """)
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
        _put(conn, close=not ok)


class DataPayload(BaseModel):
    key: str
    value: str


@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "index.html"), media_type="text/html; charset=utf-8")


@app.get("/iloom_LOGO.png", include_in_schema=False)
def logo():
    # 디렉토리 전체를 mount하면 .env까지 노출되므로 파일 하나만 명시적으로 서빙
    path = os.path.join(BASE_DIR, "iloom_LOGO.png")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="로고 파일 없음")
    return FileResponse(path, media_type="image/png")


@app.get("/api/data")
def get_data(env: Literal["main", "dev"] = "main"):
    conn = _get()
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
        _put(conn, close=not ok)


@app.post("/api/data")
def set_data(payload: DataPayload, env: Literal["main", "dev"] = "main"):
    conn = _get()
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
        _put(conn, close=not ok)
