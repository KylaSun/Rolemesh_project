import sqlite3
from pathlib import Path

# 数据库固定放在本文件旁边，避免启动位置不同产生多个数据库
DB_PATH = Path(__file__).resolve().parent / "rolemesh.db"


def get_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db():
    connection = get_connection()

    try:
        with connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS talent_profiles (
                    profile_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL UNIQUE,
                    profile_version INTEGER NOT NULL DEFAULT 1
                        CHECK (profile_version >= 1),
                    profile_json TEXT NOT NULL,
                    visibility TEXT NOT NULL DEFAULT 'private'
                        CHECK (visibility IN ('private', 'basic_card')),
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)
        connection.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        connection.commit()
        for migration in sorted((Path(__file__).resolve().parent / "migrations").glob("*.sql")):
            version = migration.stem
            if connection.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,)).fetchone():
                continue
            safe_version = version.replace("'", "''")
            try:
                connection.executescript(
                    "BEGIN IMMEDIATE;\n" + migration.read_text(encoding="utf-8")
                    + "\nINSERT INTO schema_migrations(version) VALUES ('" + safe_version + "');\nCOMMIT;"
                )
            except Exception:
                connection.rollback()
                raise
    finally:
        connection.close()


if __name__ == "__main__":
    init_db()
    print(f"数据库初始化完成：{DB_PATH}")

    connection = get_connection()
    try:
        tables = connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' ORDER BY name"
        ).fetchall()

        print("已有数据表：", [row["name"] for row in tables])
    finally:
        connection.close()