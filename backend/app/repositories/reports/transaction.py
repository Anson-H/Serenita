from dataclasses import dataclass
import sqlite3


@dataclass(frozen=True)
class ReportTransaction:
    connection: sqlite3.Connection
