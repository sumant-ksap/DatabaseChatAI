import json
import re
from collections import OrderedDict
from urllib.parse import parse_qsl, quote_plus, unquote, urlparse

import psycopg2
from psycopg2 import sql as pgsql
from psycopg2.extras import RealDictCursor

try:
    from bson import ObjectId
    from pymongo import MongoClient
except ImportError:  # pragma: no cover - handled at runtime for friendly errors
    ObjectId = None
    MongoClient = None

_db_type: str | None = None
_pg_config: dict | None = None
_mongo_config: dict | None = None
_connection_display: str = ""


# Connection management

def is_connected() -> bool:
    return _db_type is not None


def get_db_type() -> str | None:
    return _db_type


def get_connection_display() -> str:
    return _connection_display


def set_config(db_type: str = "postgres", **kwargs) -> None:
    if db_type == "mongodb":
        set_mongo_config(**kwargs)
    else:
        set_pg_config(**kwargs)


def set_pg_config(url: str = "", host: str = "", port: int = 5432,
                  database: str = "", user: str = "", password: str = "") -> None:
    global _db_type, _pg_config, _mongo_config, _connection_display
    _db_type = "postgres"
    _mongo_config = None
    if url:
        _pg_config = _parse_pg_url(url)
        _connection_display = "PostgreSQL " + _mask_url(url)
    else:
        _pg_config = {
            "host": host,
            "port": int(port) if port else 5432,
            "database": database,
            "user": user,
            "password": password,
        }
        _connection_display = f"PostgreSQL {user}@{host}:{port}/{database}"


def set_mongo_config(url: str = "", host: str = "", port: int = 27017,
                     database: str = "", user: str = "", password: str = "") -> None:
    global _db_type, _pg_config, _mongo_config, _connection_display
    if MongoClient is None:
        raise RuntimeError("MongoDB support requires pymongo. Install it with: pip install pymongo")

    _db_type = "mongodb"
    _pg_config = None
    if url:
        parsed_db = _database_from_mongo_url(url)
        _mongo_config = {"url": url, "database": database or parsed_db}
        _connection_display = "MongoDB " + _mask_url(url)
    else:
        uri = _build_mongo_uri(host, port, user, password)
        _mongo_config = {"url": uri, "database": database}
        auth_part = f"{user}@" if user else ""
        _connection_display = f"MongoDB {auth_part}{host}:{port}/{database}"


def clear_pg_config() -> None:
    clear_config()


def clear_config() -> None:
    global _db_type, _pg_config, _mongo_config, _connection_display
    _db_type = None
    _pg_config = None
    _mongo_config = None
    _connection_display = ""


def _mask_url(url: str) -> str:
    # Greedy up to the last "@" before the host so passwords containing "@" stay hidden.
    return re.sub(r"^([a-zA-Z][\w+.-]*://[^:/@]+):[^/?#]*@", r"\1:***@", url)


def _parse_pg_url(url: str) -> dict:
    """Split a postgres:// URL into psycopg2 connect() kwargs.

    Unlike libpq's own URI parser, this tolerates an unencoded "@" (or ":") in
    the password by splitting the credentials at the *last* "@" before the host.
    Percent-encoded values are decoded too, so both forms work.
    """
    match = re.match(r"^postgres(?:ql)?://(?P<rest>.*)$", url.strip(), re.IGNORECASE)
    if not match:
        raise ValueError("PostgreSQL URL must start with postgresql:// or postgres://")
    rest = match.group("rest")
    rest, _, query = rest.partition("?")

    userinfo, sep, hostpart = rest.rpartition("@")
    if not sep:
        userinfo, hostpart = "", rest
    hostport, _, dbname = hostpart.partition("/")

    if hostport.startswith("["):  # IPv6 literal, e.g. [::1]:5432
        host, _, port = hostport[1:].partition("]")
        port = port.lstrip(":")
    else:
        host, _, port = hostport.partition(":")

    user, _, password = userinfo.partition(":")
    config: dict = {
        "host": unquote(host) or "localhost",
        "port": int(port) if port else 5432,
        "dbname": unquote(dbname) or "postgres",
    }
    if user:
        config["user"] = unquote(user)
    if password:
        config["password"] = unquote(password)
    for key, value in parse_qsl(query):  # e.g. sslmode=require
        config[key] = value
    return config


def _database_from_mongo_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.split("/")[0] if path else ""


def _build_mongo_uri(host: str, port: int, user: str, password: str) -> str:
    if user:
        return f"mongodb://{quote_plus(user)}:{quote_plus(password)}@{host}:{int(port) if port else 27017}/"
    return f"mongodb://{host}:{int(port) if port else 27017}/"


def _get_pg_connection():
    if not _pg_config:
        raise RuntimeError("No PostgreSQL database connected. Please provide connection credentials.")
    return psycopg2.connect(connect_timeout=15, **_pg_config)


def _get_mongo_database():
    if not _mongo_config:
        raise RuntimeError("No MongoDB database connected. Please provide connection credentials.")
    if not _mongo_config.get("database"):
        raise RuntimeError("MongoDB database name is required.")
    client = MongoClient(_mongo_config["url"], serverSelectionTimeoutMS=5000)
    return client, client[_mongo_config["database"]]


def test_connection() -> tuple[bool, str]:
    try:
        if _db_type == "mongodb":
            client, db = _get_mongo_database()
            try:
                client.admin.command("ping")
                return True, f"MongoDB connected to {db.name}"
            finally:
                client.close()

        conn = _get_pg_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
        conn.close()
        return True, version
    except Exception as exc:
        return False, str(exc)


# Schema helpers

def get_schema_info() -> dict[str, list[dict]]:
    if _db_type == "mongodb":
        return get_mongo_schema_info()
    return get_pg_schema_info()


def get_pg_schema_info() -> dict[str, list[dict]]:
    conn = _get_pg_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # One round trip for every table/view in every user schema — a
            # per-table query is far too slow against remote databases with
            # hundreds of tables.
            cur.execute(f"""
                SELECT t.table_schema, t.table_name,
                       c.column_name, c.data_type, c.is_nullable
                FROM information_schema.tables t
                LEFT JOIN information_schema.columns c
                       ON c.table_schema = t.table_schema AND c.table_name = t.table_name
                WHERE t.table_type IN ('BASE TABLE', 'VIEW')
                  AND {_USER_SCHEMA_FILTER}
                ORDER BY (t.table_schema <> 'public'), t.table_schema, t.table_name, c.ordinal_position
            """)
            schema: dict[str, list[dict]] = {}
            for row in cur.fetchall():
                cols = schema.setdefault(_qualified_name(row["table_schema"], row["table_name"]), [])
                if row["column_name"] is not None:
                    cols.append({
                        "column_name": row["column_name"],
                        "data_type": row["data_type"],
                        "is_nullable": row["is_nullable"],
                    })
        return schema
    finally:
        conn.close()


_USER_SCHEMA_FILTER = (
    "t.table_schema NOT IN ('pg_catalog', 'information_schema') "
    "AND t.table_schema NOT LIKE 'pg\\_toast%%' AND t.table_schema NOT LIKE 'pg\\_temp%%'"
)


def _qualified_name(schema: str, table: str) -> str:
    # Keep bare names for "public" so existing single-schema databases look the same as before.
    return table if schema == "public" else f"{schema}.{table}"


def _resolve_pg_table(cur, name: str) -> tuple[str, str]:
    """Map a sidebar name ("table" or "schema.table") to its (schema, table)."""
    cur.execute(f"""
        SELECT t.table_schema, t.table_name
        FROM information_schema.tables t
        WHERE {_USER_SCHEMA_FILTER}
          AND ((t.table_schema = 'public' AND t.table_name = %s)
               OR t.table_schema || '.' || t.table_name = %s)
        ORDER BY (t.table_schema <> 'public')
        LIMIT 1
    """, (name, name))
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Table '{name}' not found.")
    return row["table_schema"], row["table_name"]


def get_pg_table_columns(name: str) -> list[dict]:
    conn = _get_pg_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            schema, table = _resolve_pg_table(cur, name)
            cur.execute("""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
            """, (schema, table))
            return [dict(col) for col in cur.fetchall()]
    finally:
        conn.close()


def get_mongo_schema_info() -> dict[str, list[dict]]:
    client, db = _get_mongo_database()
    try:
        schema: dict[str, list[dict]] = {}
        for name in sorted(db.list_collection_names()):
            fields: OrderedDict[str, set[str]] = OrderedDict()
            for doc in db[name].find({}, limit=25):
                _collect_mongo_fields(doc, fields)
            schema[name] = [
                {"column_name": key, "data_type": " | ".join(sorted(types)), "is_nullable": "YES"}
                for key, types in fields.items()
            ]
        return schema
    finally:
        client.close()


def _collect_mongo_fields(doc: dict, fields: OrderedDict[str, set[str]], prefix: str = "") -> None:
    for key, value in doc.items():
        path = f"{prefix}.{key}" if prefix else key
        fields.setdefault(path, set()).add(type(value).__name__)
        if isinstance(value, dict):
            _collect_mongo_fields(value, fields, path)


SCHEMA_TEXT_MAX_COLUMNS = 400


def describe_table_text(name: str) -> str:
    if _db_type == "mongodb":
        cols = get_mongo_schema_info().get(name)
        if cols is None:
            return f"Collection '{name}' not found."
    else:
        try:
            cols = get_pg_table_columns(name)
        except Exception as exc:
            return f"Error: {exc}"
    if not cols:
        return f"'{name}' has no columns."
    return f'"{name}": ' + ", ".join(
        f"{c['column_name']} ({c['data_type']})" + (" [nullable]" if c["is_nullable"] == "YES" else "")
        for c in cols
    )


def get_schema_text() -> str:
    try:
        schema = get_schema_info()
    except Exception as exc:
        return f"Error fetching schema: {exc}"
    if not schema:
        label = "collections" if _db_type == "mongodb" else "tables"
        return f"The connected database has no {label}."
    if _db_type == "mongodb":
        lines = ["MongoDB Database Schema, inferred from sample documents:"]
        for collection, fields in schema.items():
            defs = ", ".join(f"{f['column_name']} ({f['data_type']})" for f in fields) or "no sampled fields"
            lines.append(f'  Collection "{collection}": {defs}')
        return "\n".join(lines)

    total_columns = sum(len(cols) for cols in schema.values())
    if total_columns > SCHEMA_TEXT_MAX_COLUMNS:
        # Too big to send every column to the model — list table names grouped
        # by schema and let it fetch columns per table with describe_table.
        by_schema: OrderedDict[str, list[str]] = OrderedDict()
        for name in schema:
            schema_name = name.split(".", 1)[0] if "." in name else "public"
            by_schema.setdefault(schema_name, []).append(name)
        lines = [
            f"PostgreSQL database with {len(schema)} tables/views across {len(by_schema)} schemas. "
            "Columns are omitted because the schema is large: call describe_table with a table "
            "name to see its columns before querying it. Always use the schema-qualified "
            "names shown below in SQL (e.g. SELECT * FROM schema_name.table_name).",
        ]
        for schema_name, names in by_schema.items():
            lines.append(f'  Schema "{schema_name}" ({len(names)}): ' + ", ".join(names))
        return "\n".join(lines)

    lines = ["PostgreSQL Database Schema (use these names, schema-qualified where shown, in SQL):"]
    for table, cols in schema.items():
        col_defs = ", ".join(
            f"{c['column_name']} ({c['data_type']})" + (" [nullable]" if c["is_nullable"] == "YES" else "")
            for c in cols
        )
        lines.append(f'  Table "{table}": {col_defs}')
    return "\n".join(lines)


# Data helpers

def get_table_data(table_name: str, limit: int = 100, offset: int = 0) -> dict:
    if _db_type == "mongodb":
        return get_collection_data(table_name, limit, offset)
    return get_pg_table_data(table_name, limit, offset)


def get_pg_table_data(table_name: str, limit: int = 100, offset: int = 0) -> dict:
    conn = _get_pg_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            schema, table = _resolve_pg_table(cur, table_name)
            ident = pgsql.Identifier(schema, table)
            cur.execute(pgsql.SQL("SELECT COUNT(*) AS n FROM {}").format(ident))
            total = cur.fetchone()["n"]
            cur.execute(pgsql.SQL("SELECT * FROM {} LIMIT %s OFFSET %s").format(ident), (limit, offset))
            rows = [dict(row) for row in cur.fetchall()]
            columns = [desc[0] for desc in cur.description] if cur.description else []
        return {"columns": columns, "rows": rows, "total": int(total)}
    finally:
        conn.close()


def get_collection_data(collection_name: str, limit: int = 100, offset: int = 0) -> dict:
    client, db = _get_mongo_database()
    try:
        if collection_name not in db.list_collection_names():
            raise ValueError(f"Collection '{collection_name}' not found.")
        collection = db[collection_name]
        total = collection.count_documents({})
        docs = list(collection.find({}).skip(offset).limit(limit))
        rows = [_json_safe(doc) for doc in docs]
        columns = _mongo_columns(rows)
        return {"columns": columns, "rows": rows, "total": int(total)}
    finally:
        client.close()


def _mongo_columns(rows: list[dict]) -> list[str]:
    columns: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(key)
    return columns


def _json_safe(value):
    if ObjectId is not None and isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def execute_query(sql: str) -> list[dict]:
    if _db_type == "mongodb":
        raise RuntimeError("SQL queries are only available for PostgreSQL connections.")
    conn = _get_pg_connection()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            if cur.description:
                results = [dict(row) for row in cur.fetchall()]
            else:
                conn.commit()
                results = [{"message": f"Query executed. Rows affected: {cur.rowcount}"}]
        return results
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def find_documents(collection_name: str, filter_json: str = "{}", limit: int = 20) -> list[dict]:
    if _db_type != "mongodb":
        raise RuntimeError("MongoDB document queries are only available for MongoDB connections.")
    client, db = _get_mongo_database()
    try:
        query = json.loads(filter_json or "{}")
        docs = list(db[collection_name].find(query).limit(min(int(limit), 100)))
        return [_json_safe(doc) for doc in docs]
    finally:
        client.close()


def format_query_results(rows: list[dict], max_rows: int = 200) -> str:
    if not rows:
        return "Query returned no results."
    truncated = rows[:max_rows]
    headers = _mongo_columns(truncated)
    widths = {
        h: max(len(h), max((len(str(r.get(h, ""))) for r in truncated), default=0))
        for h in headers
    }
    sep = "+" + "+".join("-" * (widths[h] + 2) for h in headers) + "+"
    hdr = "|" + "|".join(f" {h:<{widths[h]}} " for h in headers) + "|"
    lines = [sep, hdr, sep]
    for row in truncated:
        lines.append("|" + "|".join(f" {str(row.get(h, '')):<{widths[h]}} " for h in headers) + "|")
    lines.append(sep)
    if len(rows) > max_rows:
        lines.append(f"  ... (showing {max_rows} of {len(rows)} rows)")
    return "\n".join(lines)
