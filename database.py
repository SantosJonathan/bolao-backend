"""
database.py — Suporte dual: PostgreSQL (Supabase/produção) + SQLite (local).

Em produção no Streamlit Cloud:
  - Define DATABASE_URL nos Secrets do Streamlit com a connection string do Supabase
  - Os dados persistem para sempre no PostgreSQL gratuito do Supabase

Localmente:
  - Sem DATABASE_URL → usa SQLite (bolao.db)
"""

import os
import threading
from contextlib import contextmanager

# ── Detecta qual banco usar ───────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
USE_PG = bool(DATABASE_URL)

# ══════════════════════════════════════════════════════════
#  SQLite  (local / sem DATABASE_URL)
# ══════════════════════════════════════════════════════════
if not USE_PG:
    import sqlite3
    DB_PATH = os.environ.get("BOLAO_DB_PATH", "bolao.db")
    _local  = threading.local()

    def _get_conn():
        if not hasattr(_local, "conn") or _local.conn is None:
            conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA synchronous=NORMAL")
            _local.conn = conn
        return _local.conn

    @contextmanager
    def _transaction():
        conn = _get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

# ══════════════════════════════════════════════════════════
#  PostgreSQL via pg8000  (Supabase / produção)
#  pg8000 é pure-Python — funciona em qualquer versão Python
# ══════════════════════════════════════════════════════════
else:
    import pg8000.native as pg8000
    from urllib.parse import urlparse

    _parsed = urlparse(DATABASE_URL)
    _PG_PARAMS = dict(
        host     = _parsed.hostname,
        port     = _parsed.port or 5432,
        database = _parsed.path.lstrip("/"),
        user     = _parsed.username,
        password = _parsed.password,
        ssl_context = True,   # Supabase exige SSL
    )

    # Conexão simples por thread (pg8000 não tem pool nativo leve)
    _local_pg = threading.local()

    def _get_conn():
        if not getattr(_local_pg, "conn", None):
            _local_pg.conn = pg8000.Connection(**_PG_PARAMS)
        return _local_pg.conn

    def _reset_conn():
        try:
            if getattr(_local_pg, "conn", None):
                _local_pg.conn.close()
        except Exception:
            pass
        _local_pg.conn = None

    @contextmanager
    def _transaction():
        try:
            conn = _get_conn()
            yield conn
            conn.run("COMMIT")
        except Exception:
            try:
                _get_conn().run("ROLLBACK")
            except Exception:
                _reset_conn()
            raise

    def _rows(result, columns):
        """Converte resultado pg8000 em lista de dicts."""
        return [dict(zip(columns, row)) for row in result]


# ══════════════════════════════════════════════════════════
#  INIT / MIGRATIONS
# ══════════════════════════════════════════════════════════

def init_db():
    if USE_PG:
        _init_postgres()
    else:
        _init_sqlite()


def _init_sqlite():
    conn = _get_conn()
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    current = 0
    if "schema_version" in tables:
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        current = row[0] if row else 0

    for i, sql in enumerate(_migrations_sqlite()):
        if current < i + 1:
            try:
                conn.executescript(sql)
                current = i + 1
            except Exception as e:
                import sys
                print(f"[bolao] SQLite migration v{i+1} failed: {e}", file=sys.stderr)


def _init_postgres():
    conn = _get_conn()
    try:
        conn.run("BEGIN")
        conn.run("""
            CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)
        """)
        rows = conn.run("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        current = rows[0][0] if rows else 0

        for i, sql in enumerate(_migrations_postgres()):
            if current < i + 1:
                try:
                    conn.run(sql)
                    if current == 0 and i == 0:
                        conn.run("INSERT INTO schema_version VALUES (:v)", v=i+1)
                    else:
                        conn.run("UPDATE schema_version SET version = :v", v=i+1)
                    current = i + 1
                except Exception as e:
                    import sys
                    print(f"[bolao] PG migration v{i+1} failed: {e}", file=sys.stderr)
        conn.run("COMMIT")
    except Exception:
        try: conn.run("ROLLBACK")
        except: _reset_conn()


def _migrations_sqlite():
    return [
        """
        CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
        INSERT OR IGNORE INTO schema_version VALUES (0);
        CREATE TABLE IF NOT EXISTS participantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL UNIQUE COLLATE NOCASE,
            enviado_em DATETIME DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS palpites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participante_id INTEGER NOT NULL,
            jogo TEXT NOT NULL CHECK(jogo IN ('jogo1','jogo2','jogo3')),
            gols_brasil INTEGER NOT NULL CHECK(gols_brasil >= 0),
            gols_adversario INTEGER NOT NULL CHECK(gols_adversario >= 0),
            enviado_em DATETIME DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (participante_id) REFERENCES participantes(id),
            UNIQUE(participante_id, jogo)
        );
        CREATE TABLE IF NOT EXISTS classificacao_palpites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participante_id INTEGER NOT NULL UNIQUE,
            primeiro TEXT NOT NULL, segundo TEXT NOT NULL,
            terceiro TEXT NOT NULL, quarto TEXT NOT NULL,
            enviado_em DATETIME DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (participante_id) REFERENCES participantes(id)
        );
        CREATE TABLE IF NOT EXISTS placares_reais (
            jogo TEXT PRIMARY KEY CHECK(jogo IN ('jogo1','jogo2','jogo3')),
            gols_brasil INTEGER, gols_adversario INTEGER,
            encerrado INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS classificacao_real (
            posicao INTEGER PRIMARY KEY CHECK(posicao BETWEEN 1 AND 4),
            time TEXT NOT NULL
        );
        INSERT OR IGNORE INTO placares_reais (jogo,encerrado) VALUES ('jogo1',0);
        INSERT OR IGNORE INTO placares_reais (jogo,encerrado) VALUES ('jogo2',0);
        INSERT OR IGNORE INTO placares_reais (jogo,encerrado) VALUES ('jogo3',0);
        UPDATE schema_version SET version = 1;
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_pal_part ON palpites(participante_id);
        CREATE INDEX IF NOT EXISTS idx_pal_jogo ON palpites(jogo);
        UPDATE schema_version SET version = 2;
        """,
    ]


def _migrations_postgres():
    return [
        """
        CREATE TABLE IF NOT EXISTS participantes (
            id SERIAL PRIMARY KEY,
            nome TEXT NOT NULL,
            enviado_em TIMESTAMP DEFAULT NOW(),
            UNIQUE(nome)
        );
        CREATE TABLE IF NOT EXISTS palpites (
            id SERIAL PRIMARY KEY,
            participante_id INTEGER NOT NULL REFERENCES participantes(id),
            jogo TEXT NOT NULL CHECK(jogo IN ('jogo1','jogo2','jogo3')),
            gols_brasil INTEGER NOT NULL CHECK(gols_brasil >= 0),
            gols_adversario INTEGER NOT NULL CHECK(gols_adversario >= 0),
            enviado_em TIMESTAMP DEFAULT NOW(),
            UNIQUE(participante_id, jogo)
        );
        CREATE TABLE IF NOT EXISTS classificacao_palpites (
            id SERIAL PRIMARY KEY,
            participante_id INTEGER NOT NULL UNIQUE REFERENCES participantes(id),
            primeiro TEXT NOT NULL, segundo TEXT NOT NULL,
            terceiro TEXT NOT NULL, quarto TEXT NOT NULL,
            enviado_em TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS placares_reais (
            jogo TEXT PRIMARY KEY CHECK(jogo IN ('jogo1','jogo2','jogo3')),
            gols_brasil INTEGER, gols_adversario INTEGER,
            encerrado INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS classificacao_real (
            posicao INTEGER PRIMARY KEY CHECK(posicao BETWEEN 1 AND 4),
            time TEXT NOT NULL
        );
        INSERT INTO placares_reais (jogo,encerrado) VALUES ('jogo1',0),('jogo2',0),('jogo3',0)
        ON CONFLICT (jogo) DO NOTHING;
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_pal_part ON palpites(participante_id);
        CREATE INDEX IF NOT EXISTS idx_pal_jogo ON palpites(jogo);
        """,
    ]


# ══════════════════════════════════════════════════════════
#  LEITURAS
# ══════════════════════════════════════════════════════════

def get_all_participantes():
    if USE_PG:
        conn = _get_conn()
        result = conn.run("SELECT id, nome, enviado_em FROM participantes ORDER BY enviado_em")
        return [(r[0], r[1], str(r[2])) for r in result]
    else:
        rows = _get_conn().execute(
            "SELECT id, nome, enviado_em FROM participantes ORDER BY enviado_em"
        ).fetchall()
        return [(r["id"], r["nome"], r["enviado_em"]) for r in rows]


def get_palpites_by_participante(pid: int) -> dict:
    if USE_PG:
        conn   = _get_conn()
        result = conn.run(
            "SELECT jogo, gols_brasil, gols_adversario FROM palpites WHERE participante_id=:pid",
            pid=pid
        )
        return {r[0]: (r[1], r[2]) for r in result}
    else:
        rows = _get_conn().execute(
            "SELECT jogo, gols_brasil, gols_adversario FROM palpites WHERE participante_id=?",
            (pid,)
        ).fetchall()
        return {r["jogo"]: (r["gols_brasil"], r["gols_adversario"]) for r in rows}


def get_classificacao_palpite(pid: int):
    if USE_PG:
        conn   = _get_conn()
        result = conn.run(
            "SELECT primeiro,segundo,terceiro,quarto FROM classificacao_palpites WHERE participante_id=:pid",
            pid=pid
        )
        return tuple(result[0]) if result else None
    else:
        row = _get_conn().execute(
            "SELECT primeiro,segundo,terceiro,quarto FROM classificacao_palpites WHERE participante_id=?",
            (pid,)
        ).fetchone()
        return tuple(row) if row else None


def get_placares_reais() -> dict:
    if USE_PG:
        conn   = _get_conn()
        result = conn.run(
            "SELECT jogo, gols_brasil, gols_adversario, encerrado FROM placares_reais"
        )
        return {r[0]: {"brasil": r[1], "adversario": r[2], "encerrado": r[3]} for r in result}
    else:
        rows = _get_conn().execute(
            "SELECT jogo, gols_brasil, gols_adversario, encerrado FROM placares_reais"
        ).fetchall()
        return {r["jogo"]: {"brasil": r["gols_brasil"], "adversario": r["gols_adversario"], "encerrado": r["encerrado"]} for r in rows}


def get_classificacao_real() -> dict:
    if USE_PG:
        result = _get_conn().run("SELECT posicao, time FROM classificacao_real ORDER BY posicao")
        return {r[0]: r[1] for r in result}
    else:
        rows = _get_conn().execute(
            "SELECT posicao, time FROM classificacao_real ORDER BY posicao"
        ).fetchall()
        return {r["posicao"]: r["time"] for r in rows}


def palpite_enviado(nome: str) -> bool:
    if USE_PG:
        conn   = _get_conn()
        result = conn.run("SELECT id FROM participantes WHERE LOWER(nome)=LOWER(:nome)", nome=nome)
        if not result:
            return False
        pid    = result[0][0]
        count  = conn.run("SELECT COUNT(*) FROM palpites WHERE participante_id=:pid", pid=pid)
        return count[0][0] > 0
    else:
        conn = _get_conn()
        row  = conn.execute("SELECT id FROM participantes WHERE nome=?", (nome,)).fetchone()
        if not row:
            return False
        count = conn.execute(
            "SELECT COUNT(*) as c FROM palpites WHERE participante_id=?", (row["id"],)
        ).fetchone()["c"]
        return count > 0


def get_palpite_completo_por_nome(nome: str):
    if USE_PG:
        conn   = _get_conn()
        result = conn.run(
            "SELECT id, enviado_em FROM participantes WHERE LOWER(nome)=LOWER(:nome)", nome=nome
        )
        if not result:
            return None
        pid, enviado_em = result[0][0], str(result[0][1])
    else:
        conn = _get_conn()
        row  = conn.execute("SELECT id, enviado_em FROM participantes WHERE nome=?", (nome,)).fetchone()
        if not row:
            return None
        pid, enviado_em = row["id"], row["enviado_em"]
    return {
        "pid":        pid,
        "enviado_em": enviado_em,
        "palpites":   get_palpites_by_participante(pid),
        "classif":    get_classificacao_palpite(pid),
    }


# ══════════════════════════════════════════════════════════
#  ESCRITAS
# ══════════════════════════════════════════════════════════

def save_palpite(nome: str, palpites: dict, classificacao: tuple) -> bool:
    if USE_PG:
        conn = _get_conn()
        try:
            conn.run("BEGIN")
            conn.run(
                "INSERT INTO participantes (nome) VALUES (:nome) ON CONFLICT (nome) DO NOTHING",
                nome=nome
            )
            result = conn.run(
                "SELECT id FROM participantes WHERE LOWER(nome)=LOWER(:nome)", nome=nome
            )
            pid = result[0][0]
            count = conn.run(
                "SELECT COUNT(*) FROM palpites WHERE participante_id=:pid", pid=pid
            )[0][0]
            if count > 0:
                conn.run("ROLLBACK")
                return False
            for jogo, (gb, ga) in palpites.items():
                conn.run(
                    """INSERT INTO palpites (participante_id,jogo,gols_brasil,gols_adversario)
                       VALUES (:pid,:jogo,:gb,:ga) ON CONFLICT (participante_id,jogo) DO NOTHING""",
                    pid=pid, jogo=jogo, gb=gb, ga=ga
                )
            conn.run(
                """INSERT INTO classificacao_palpites
                   (participante_id,primeiro,segundo,terceiro,quarto)
                   VALUES (:pid,:c1,:c2,:c3,:c4)
                   ON CONFLICT (participante_id) DO NOTHING""",
                pid=pid, c1=classificacao[0], c2=classificacao[1],
                c3=classificacao[2], c4=classificacao[3]
            )
            conn.run("COMMIT")
            return True
        except Exception:
            try: conn.run("ROLLBACK")
            except: _reset_conn()
            raise
    else:
        with _transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO participantes (nome) VALUES (?)", (nome,))
            row = conn.execute("SELECT id FROM participantes WHERE nome=?", (nome,)).fetchone()
            pid = row["id"]
            already = conn.execute(
                "SELECT COUNT(*) as c FROM palpites WHERE participante_id=?", (pid,)
            ).fetchone()["c"]
            if already > 0:
                return False
            for jogo, (gb, ga) in palpites.items():
                conn.execute(
                    """INSERT OR IGNORE INTO palpites
                       (participante_id,jogo,gols_brasil,gols_adversario) VALUES (?,?,?,?)""",
                    (pid, jogo, gb, ga)
                )
            conn.execute(
                """INSERT OR IGNORE INTO classificacao_palpites
                   (participante_id,primeiro,segundo,terceiro,quarto) VALUES (?,?,?,?,?)""",
                (pid, *classificacao)
            )
        return True


def save_placar_real(jogo: str, gols_brasil: int, gols_adversario: int):
    if USE_PG:
        conn = _get_conn()
        conn.run("BEGIN")
        conn.run(
            "UPDATE placares_reais SET gols_brasil=:gb, gols_adversario=:ga, encerrado=1 WHERE jogo=:jogo",
            gb=gols_brasil, ga=gols_adversario, jogo=jogo
        )
        conn.run("COMMIT")
    else:
        with _transaction() as conn:
            conn.execute(
                "UPDATE placares_reais SET gols_brasil=?,gols_adversario=?,encerrado=1 WHERE jogo=?",
                (gols_brasil, gols_adversario, jogo)
            )


def save_classificacao_real(ordem: list):
    if USE_PG:
        conn = _get_conn()
        conn.run("BEGIN")
        for i, time in enumerate(ordem, 1):
            conn.run(
                """INSERT INTO classificacao_real (posicao,time) VALUES (:pos,:time)
                   ON CONFLICT (posicao) DO UPDATE SET time=EXCLUDED.time""",
                pos=i, time=time
            )
        conn.run("COMMIT")
    else:
        with _transaction() as conn:
            for i, time in enumerate(ordem, 1):
                conn.execute(
                    """INSERT INTO classificacao_real (posicao,time) VALUES (?,?)
                       ON CONFLICT(posicao) DO UPDATE SET time=excluded.time""",
                    (i, time)
                )
