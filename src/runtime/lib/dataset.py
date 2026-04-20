"""Dataset: unified data access tool for SQLite, HTTP, and future adapters."""

import sqlite3
from abc import ABC, abstractmethod


class _Adapter(ABC):
    @abstractmethod
    def query(self, filters: dict, limit: int, offset: int) -> list[dict]:
        ...

    @abstractmethod
    def get(self, field: str, value) -> dict | None:
        ...

    @abstractmethod
    def create(self, data: dict) -> dict:
        ...

    @abstractmethod
    def update(self, field: str, value, data: dict) -> dict:
        ...

    @abstractmethod
    def delete(self, field: str, value) -> bool:
        ...

    @abstractmethod
    def count(self, filters: dict | None) -> int:
        ...


class _SQLiteAdapter(_Adapter):
    def __init__(self, cfg: dict):
        self._connection = cfg["connection"]
        self._table = cfg["table"]
        self._primary_key = cfg.get("primaryKey", "id")

    def _conn(self):
        return sqlite3.connect(self._connection)

    def _row_to_dict(self, cursor, row) -> dict:
        return {desc[0]: row[i] for i, desc in enumerate(cursor.description)}

    def query(self, filters: dict, limit: int, offset: int) -> list[dict]:
        where, params = self._build_where(filters)
        sql = f"SELECT * FROM {self._table}{where} LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        with self._conn() as conn:
            conn.row_factory = self._row_to_dict
            cur = conn.execute(sql, params)
            return cur.fetchall()

    def get(self, field: str, value) -> dict | None:
        sql = f"SELECT * FROM {self._table} WHERE {field} = ? LIMIT 1"
        with self._conn() as conn:
            conn.row_factory = self._row_to_dict
            cur = conn.execute(sql, (value,))
            return cur.fetchone()

    def create(self, data: dict) -> dict:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        sql = f"INSERT INTO {self._table} ({columns}) VALUES ({placeholders})"
        with self._conn() as conn:
            cur = conn.execute(sql, tuple(data.values()))
            conn.commit()
            pk_val = data.get(self._primary_key) or cur.lastrowid
            return self.get(self._primary_key, pk_val) or data

    def update(self, field: str, value, data: dict) -> dict:
        if not data:
            existing = self.get(field, value)
            return existing or {}
        sets = ", ".join([f"{k} = ?" for k in data.keys()])
        sql = f"UPDATE {self._table} SET {sets} WHERE {field} = ?"
        params = list(data.values()) + [value]
        with self._conn() as conn:
            conn.execute(sql, params)
            conn.commit()
            return self.get(field, value) or data

    def delete(self, field: str, value) -> bool:
        sql = f"DELETE FROM {self._table} WHERE {field} = ?"
        with self._conn() as conn:
            cur = conn.execute(sql, (value,))
            conn.commit()
            return cur.rowcount > 0

    def count(self, filters: dict | None) -> int:
        where, params = self._build_where(filters or {})
        sql = f"SELECT COUNT(*) as c FROM {self._table}{where}"
        with self._conn() as conn:
            cur = conn.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row else 0

    def _build_where(self, filters: dict) -> tuple[str, list]:
        if not filters:
            return "", []
        clauses = []
        params = []
        for k, v in filters.items():
            if isinstance(v, list):
                placeholders = ", ".join(["?"] * len(v))
                clauses.append(f"{k} IN ({placeholders})")
                params.extend(v)
            else:
                clauses.append(f"{k} = ?")
                params.append(v)
        return " WHERE " + " AND ".join(clauses), params


class _HttpAdapter(_Adapter):
    def __init__(self, cfg: dict):
        self._cfg = cfg

    def query(self, filters: dict, limit: int, offset: int) -> list[dict]:
        raise NotImplementedError("HttpAdapter.query not yet implemented")

    def get(self, field: str, value) -> dict | None:
        raise NotImplementedError("HttpAdapter.get not yet implemented")

    def create(self, data: dict) -> dict:
        raise NotImplementedError("HttpAdapter.create not yet implemented")

    def update(self, field: str, value, data: dict) -> dict:
        raise NotImplementedError("HttpAdapter.update not yet implemented")

    def delete(self, field: str, value) -> bool:
        raise NotImplementedError("HttpAdapter.delete not yet implemented")

    def count(self, filters: dict | None) -> int:
        raise NotImplementedError("HttpAdapter.count not yet implemented")


_ADAPTERS = {
    "sqlite": _SQLiteAdapter,
    "api": _HttpAdapter,
}


def _create_adapter(type_: str, cfg: dict) -> _Adapter:
    cls = _ADAPTERS.get(type_)
    if cls is None:
        raise ValueError(f"Unsupported dataset type: {type_}")
    return cls(cfg)


class Dataset:
    """Unified data access wrapper that auto-selects adapter and handles fieldMap."""

    def __init__(self, cfg: dict):
        self._cfg = cfg
        self._adapter = _create_adapter(cfg["type"], cfg)
        self._field_map = cfg.get("fieldMap", {})
        self._reverse_map = {v: k for k, v in self._field_map.items()}
        self._primary_key = cfg.get("primaryKey", "id")

    def query(self, filters: dict, limit: int = 50, offset: int = 0) -> list[dict]:
        mapped_filters = self._to_external(filters)
        results = self._adapter.query(mapped_filters, limit, offset)
        return [self._to_model(r) for r in results]

    def get(self, id: str) -> dict | None:
        external_pk = self._field_map.get(self._primary_key, self._primary_key)
        result = self._adapter.get(external_pk, id)
        return self._to_model(result) if result else None

    def create(self, data: dict) -> dict:
        mapped = self._to_external(data)
        result = self._adapter.create(mapped)
        return self._to_model(result)

    def update(self, id: str, data: dict) -> dict:
        external_pk = self._field_map.get(self._primary_key, self._primary_key)
        mapped = self._to_external(data)
        result = self._adapter.update(external_pk, id, mapped)
        return self._to_model(result)

    def delete(self, id: str) -> bool:
        external_pk = self._field_map.get(self._primary_key, self._primary_key)
        return self._adapter.delete(external_pk, id)

    def count(self, filters: dict | None = None) -> int:
        mapped_filters = self._to_external(filters or {})
        return self._adapter.count(mapped_filters)

    def _to_external(self, data: dict) -> dict:
        if not self._field_map:
            return data
        return {self._field_map.get(k, k): v for k, v in data.items()}

    def _to_model(self, data: dict) -> dict:
        if not self._reverse_map:
            return data
        return {self._reverse_map.get(k, k): v for k, v in data.items()}
