"""SQLite persistence for versioned BSP sections and embeddings."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
import re
import sqlite3

import numpy as np
import numpy.typing as npt

from .parser import DocumentChunk


_TOKEN_RE = re.compile(r"[\w.]+", re.UNICODE)


class IndexDatabase:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"BSP index does not exist: {self.path}")
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row

    @classmethod
    def create(
        cls, path: str | Path, metadata: Mapping[str, str]
    ) -> "IndexDatabase":
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(target)
        connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE sections (
                id TEXT PRIMARY KEY,
                source_version TEXT NOT NULL,
                anchor TEXT NOT NULL,
                source_path TEXT NOT NULL,
                title TEXT NOT NULL,
                breadcrumb TEXT NOT NULL,
                text TEXT NOT NULL,
                part INTEGER NOT NULL,
                has_recommendation INTEGER NOT NULL,
                has_warning INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                embedding_dim INTEGER NOT NULL
            );
            CREATE VIRTUAL TABLE sections_fts USING fts5(
                id UNINDEXED, title, breadcrumb, text,
                tokenize='unicode61 remove_diacritics 2'
            );
            CREATE TABLE query_cache (
                cache_key TEXT PRIMARY KEY,
                embedding BLOB NOT NULL,
                embedding_dim INTEGER NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items()
        )
        connection.commit()
        connection.close()
        return cls(target)

    def __enter__(self) -> "IndexDatabase":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def metadata(self) -> dict[str, str]:
        return {
            row["key"]: row["value"]
            for row in self.connection.execute("SELECT key, value FROM metadata")
        }

    def add_chunks(
        self,
        chunks: Sequence[DocumentChunk],
        vectors: npt.NDArray[np.float32],
    ) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("Chunk and embedding counts differ")
        section_rows = []
        fts_rows = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            normalized = np.asarray(vector, dtype=np.float32)
            breadcrumb = " > ".join(chunk.breadcrumb)
            section_rows.append(
                (
                    chunk.id,
                    chunk.source_version,
                    chunk.anchor,
                    chunk.source_path,
                    chunk.title,
                    json.dumps(chunk.breadcrumb, ensure_ascii=False),
                    chunk.text,
                    chunk.part,
                    int(chunk.has_recommendation),
                    int(chunk.has_warning),
                    normalized.tobytes(),
                    normalized.size,
                )
            )
            fts_rows.append((chunk.id, chunk.title, breadcrumb, chunk.text))
        with self.connection:
            self.connection.executemany(
                """INSERT INTO sections VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                section_rows,
            )
            self.connection.executemany(
                "INSERT INTO sections_fts(id, title, breadcrumb, text) VALUES (?, ?, ?, ?)",
                fts_rows,
            )

    def get_section(self, section_id: str) -> dict[str, object] | None:
        row = self.connection.execute(
            """SELECT id, source_version, anchor, source_path, title, breadcrumb, text, part,
                      has_recommendation, has_warning
               FROM sections WHERE id = ?""",
            (section_id,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["breadcrumb"] = json.loads(str(result["breadcrumb"]))
        result["has_recommendation"] = bool(result["has_recommendation"])
        result["has_warning"] = bool(result["has_warning"])
        return result

    def get_sections(self, ids: Sequence[str]) -> dict[str, dict[str, object]]:
        return {
            section_id: section
            for section_id in ids
            if (section := self.get_section(section_id)) is not None
        }

    def all_vectors(
        self,
        *,
        mode: str = "all",
        subsystem: str | None = None,
        api_group: str | None = None,
    ) -> tuple[list[str], npt.NDArray[np.float32]]:
        where, parameters = _scope_sql(mode, subsystem, api_group)
        rows = self.connection.execute(
            f"SELECT id, embedding, embedding_dim FROM sections{where} ORDER BY rowid",
            parameters,
        ).fetchall()
        ids = [str(row["id"]) for row in rows]
        if not rows:
            return ids, np.empty((0, 0), dtype=np.float32)
        vectors = [
            np.frombuffer(row["embedding"], dtype=np.float32, count=row["embedding_dim"])
            for row in rows
        ]
        return ids, np.vstack(vectors)

    def section_ids(
        self,
        *,
        mode: str = "all",
        subsystem: str | None = None,
        api_group: str | None = None,
    ) -> list[str]:
        where, parameters = _scope_sql(mode, subsystem, api_group)
        rows = self.connection.execute(
            f"SELECT id FROM sections{where} ORDER BY rowid", parameters
        ).fetchall()
        return [str(row["id"]) for row in rows]

    def fts_candidates(
        self,
        query: str,
        limit: int,
        *,
        mode: str = "all",
        subsystem: str | None = None,
        api_group: str | None = None,
    ) -> list[tuple[str, float]]:
        tokens = _TOKEN_RE.findall(query)
        if not tokens:
            return []
        expression = " OR ".join(f'"{token.replace(chr(34), chr(34) * 2)}"' for token in tokens)
        scope_where, scope_parameters = _scope_sql(
            mode, subsystem, api_group, prefix="sections."
        )
        conjunction = " AND " + scope_where.removeprefix(" WHERE ") if scope_where else ""
        rows = self.connection.execute(
            f"""SELECT sections_fts.id,
                       bm25(sections_fts, 0.0, 3.0, 2.0, 1.0) AS score
                  FROM sections_fts
                  JOIN sections ON sections.id = sections_fts.id
                 WHERE sections_fts MATCH ?{conjunction}
                 ORDER BY score LIMIT ?""",
            (expression, *scope_parameters, limit),
        ).fetchall()
        return [(str(row["id"]), float(row["score"])) for row in rows]

    def get_cached_query(self, cache_key: str) -> npt.NDArray[np.float32] | None:
        row = self.connection.execute(
            "SELECT embedding, embedding_dim FROM query_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        return np.frombuffer(
            row["embedding"], dtype=np.float32, count=row["embedding_dim"]
        ).copy()

    def cache_query(self, cache_key: str, vector: npt.NDArray[np.float32]) -> None:
        normalized = np.asarray(vector, dtype=np.float32)
        with self.connection:
            self.connection.execute(
                """INSERT OR REPLACE INTO query_cache(cache_key, embedding, embedding_dim)
                   VALUES (?, ?, ?)""",
                (cache_key, normalized.tobytes(), normalized.size),
            )


def _scope_sql(
    mode: str,
    subsystem: str | None,
    api_group: str | None = None,
    *,
    prefix: str = "",
) -> tuple[str, tuple[str, ...]]:
    if mode not in {"all", "development", "override"}:
        raise ValueError("mode must be one of: all, development, override")

    clauses: list[str] = []
    parameters: list[str] = []
    source_path = f"replace({prefix}source_path, '\\', '/')"
    root = "Глава 4. Программный интерфейс"
    if mode == "development":
        clauses.append(f"{source_path} LIKE ?")
        parameters.append(f"{root}/%/Интерфейс/%")
    elif mode == "override":
        clauses.append(f"{source_path} LIKE ?")
        parameters.append(f"{root}/%/Переопределение/%")

    if subsystem:
        clauses.append(f"{source_path} LIKE ?")
        parameters.append(f"{root}/{subsystem}/%")

    if api_group:
        if not subsystem:
            raise ValueError("subsystem is required when api_group is specified")
        interface_kind = {
            "development": "Интерфейс",
            "override": "Переопределение",
        }.get(mode)
        if api_group == "Основные процедуры и функции":
            if interface_kind:
                clauses.append(f"{source_path} LIKE ?")
                parameters.append(f"{root}/{subsystem}/{interface_kind}/%")
                clauses.append(f"{source_path} NOT LIKE ?")
                parameters.append(f"{root}/{subsystem}/{interface_kind}/%/%")
            else:
                clauses.append(
                    f"({source_path} LIKE ? OR {source_path} LIKE ?)"
                )
                parameters.extend(
                    (
                        f"{root}/{subsystem}/Интерфейс/%",
                        f"{root}/{subsystem}/Переопределение/%",
                    )
                )
                clauses.append(
                    f"({source_path} NOT LIKE ? AND {source_path} NOT LIKE ?)"
                )
                parameters.extend(
                    (
                        f"{root}/{subsystem}/Интерфейс/%/%",
                        f"{root}/{subsystem}/Переопределение/%/%",
                    )
                )
        elif interface_kind:
            clauses.append(f"{source_path} LIKE ?")
            parameters.append(f"{root}/{subsystem}/{interface_kind}/{api_group}/%")
        else:
            clauses.append(f"{source_path} LIKE ?")
            parameters.append(f"{root}/{subsystem}/%/{api_group}/%")

    if not clauses:
        return "", ()
    return " WHERE " + " AND ".join(clauses), tuple(parameters)
