"""Load named SQL statements from a reloadable text file.

The file is intentionally checked by modification time on every lookup. This
lets operators update a runtime query without restarting the API process.
"""

from pathlib import Path
import re
import threading


DEFAULT_QUERY_FILE = Path(__file__).resolve().parents[1] / "queries" / "queries.txt"


class QueryStore:
    def __init__(self, path: Path = DEFAULT_QUERY_FILE):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._mtime_ns: int | None = None
        self._queries: dict[str, str] = {}

    def get(self, name: str | int, *, dialect: str | None = None) -> str:
        """Load a numbered query and optionally activate its SQL Server clause.

        A '-- @mssql ...' line keeps the return-ID clause beside its INSERT,
        avoiding a second copy of the whole statement for SQL Server.
        """
        name = str(name)
        with self._lock:
            mtime_ns = self.path.stat().st_mtime_ns
            if mtime_ns != self._mtime_ns:
                self._queries = self._parse(self.path.read_text(encoding="utf-8"))
                self._mtime_ns = mtime_ns
            try:
                query = self._queries[name]
            except KeyError as exc:
                raise KeyError(f"SQL query '{name}' is not defined in {self.path}") from exc
            if dialect is not None:
                query = re.sub(
                    r"(?m)^--\s*@mssql\s+(.+)$",
                    lambda match: match.group(1) if dialect == "mssql" else "",
                    query,
                )
            return query

    @staticmethod
    def _parse(contents: str) -> dict[str, str]:
        queries: dict[str, str] = {}
        current_name: str | None = None
        current_lines: list[str] = []

        def save_current() -> None:
            if current_name is None:
                return
            query = "\n".join(current_lines).strip()
            if not query:
                raise ValueError(f"SQL query '{current_name}' is empty")
            if current_name in queries:
                raise ValueError(f"SQL query '{current_name}' is defined more than once")
            queries[current_name] = query

        for line in contents.splitlines():
            marker = re.match(r"^--\s*(\d+)\s*:\s*(.+?)\s*$", line)
            if marker:
                save_current()
                current_name = marker.group(1)
                current_lines = []
            elif current_name is not None:
                current_lines.append(line)

        save_current()
        if not queries:
            raise ValueError("SQL query file does not contain any numbered '-- 1: description' sections")
        return queries


query_store = QueryStore()
