from __future__ import annotations
import sqlite3
import pytest
from backend.app.storage.conversation_database import CONVERSATION_DATABASE_SCHEMA
from backend.app.storage.report_database import REPORT_DATABASE_SCHEMA
from backend.app.storage.auth_database import AUTH_DATABASE_SCHEMA
from backend.app.storage.config_database import CONFIG_DATABASE_SCHEMA
from backend.app.storage.favorite_database import FAVORITES_DATABASE_SCHEMA
from backend.app.storage.member_database import MEMBER_DATABASE_SCHEMA
from backend.app.storage.schema import CheckConstraint, Column, ColumnGroup, Database, ForeignKey, Index, Table, UniqueConstraint
from backend.app.storage.sqlite import UnsupportedSchemaError
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from threading import Event
from backend.app.storage import config_database
from backend.app.storage.paths import app_paths


DATABASE_SCHEMAS = (
    AUTH_DATABASE_SCHEMA,
    CONFIG_DATABASE_SCHEMA,
    FAVORITES_DATABASE_SCHEMA,
    MEMBER_DATABASE_SCHEMA,
    CONVERSATION_DATABASE_SCHEMA,
    REPORT_DATABASE_SCHEMA,
)


def test_every_database_is_created_and_validated_from_the_ordered_contract(tmp_path):
    for database in DATABASE_SCHEMAS:
        path = tmp_path / database.name
        with sqlite3.connect(path) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            database.create(connection)

        assert database.validate_existing(path)
        with sqlite3.connect(path) as connection:
            for table in database.tables:
                actual_columns = tuple(
                    str(row[1])
                    for row in connection.execute(
                        f'PRAGMA table_info("{table.name}")'
                    )
                )
                assert actual_columns == table.column_names


def test_resource_tables_share_one_file_metadata_contract():
    conversation_table = CONVERSATION_DATABASE_SCHEMA.table_by_name[
        "conversation_resources"
    ]
    report_table = REPORT_DATABASE_SCHEMA.table_by_name["report_sources"]
    shared_names = (
        "mime_type",
        "size_bytes",
        "relative_path",
        "sha256",
    )

    for table in (conversation_table, report_table):
        names = table.column_names
        positions = tuple(names.index(name) for name in shared_names)
        assert positions == tuple(
            range(positions[0], positions[0] + len(shared_names))
        )

    conversation_columns = {
        column.name: column.sql() for column in conversation_table.columns
    }
    report_columns = {column.name: column.sql() for column in report_table.columns}
    assert {
        name: conversation_columns[name] for name in shared_names
    } == {
        name: report_columns[name] for name in shared_names
    }
    assert report_table.column_names[-1] == "created_at"
    assert "original_filename" not in report_table.column_names
    assert "uploaded_at" not in report_table.column_names


def test_same_named_columns_share_one_column_definition():
    columns_by_name = {}
    for database in DATABASE_SCHEMAS:
        for table in database.tables:
            for column in table.columns:
                columns_by_name.setdefault(column.name, []).append(column)

    nullable_variants = {
        "expires_at": {"expires_at TEXT", "expires_at TEXT NOT NULL"},
        "member_id": {"member_id TEXT", "member_id TEXT NOT NULL"},
    }
    for name, columns in columns_by_name.items():
        if len(columns) < 2:
            continue
        definitions = {column.sql() for column in columns}
        if name in nullable_variants:
            assert definitions == nullable_variants[name]
        else:
            assert len(definitions) == 1, (name, definitions)


def test_defaulted_application_values_are_not_nullable():
    for database in DATABASE_SCHEMAS:
        for table in database.tables:
            for column in table.columns:
                if column.default is not None:
                    assert not column.nullable, (
                        database.name,
                        table.name,
                        column.name,
                    )


def test_shared_columns_keep_the_same_relative_order_in_every_table():
    tables = [
        table
        for database in DATABASE_SCHEMAS
        for table in database.tables
    ]
    for left_index, left in enumerate(tables):
        for right in tables[left_index + 1 :]:
            shared = set(left.column_names) & set(right.column_names)
            left_order = tuple(name for name in left.column_names if name in shared)
            right_order = tuple(name for name in right.column_names if name in shared)
            assert left_order == right_order, (
                left.name,
                right.name,
                left_order,
                right_order,
            )


def test_database_validation_rejects_column_reordering(tmp_path):
    path = tmp_path / "auth.db"
    with sqlite3.connect(path) as connection:
        AUTH_DATABASE_SCHEMA.create(connection)
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute("ALTER TABLE login_sessions RENAME TO old_login_sessions")
        connection.execute(
            """
            CREATE TABLE login_sessions (
                account_id TEXT NOT NULL,
                session_token_hash TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (session_token_hash),
                FOREIGN KEY (account_id) REFERENCES accounts (account_id)
                    ON UPDATE NO ACTION ON DELETE NO ACTION
            )
            """
        )
        connection.execute("DROP TABLE old_login_sessions")

    original = path.read_bytes()
    with pytest.raises(UnsupportedSchemaError, match="column order"):
        AUTH_DATABASE_SCHEMA.validate_existing(path)
    assert path.read_bytes() == original


def test_database_validation_rejects_a_missing_column(tmp_path):
    database = _validation_contract()
    path = tmp_path / database.name
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE parents (parent_id TEXT NOT NULL, PRIMARY KEY (parent_id))"
        )
        connection.execute(database.tables[1].create_table_sql())

    with pytest.raises(UnsupportedSchemaError, match="column order"):
        database.validate_existing(path)


def _validation_contract(
    *,
    value_default: str = "'ready'",
    include_unique: bool = True,
    check_expression: str = "length(value) > 0",
    on_delete: str = "CASCADE",
    index_name: str = "records_by_value",
) -> Database:
    parent = Table(
        name="parents",
        columns=(
            Column("parent_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
            Column("value", "TEXT", ColumnGroup.DATA, nullable=False, default=value_default),
        ),
        primary_key=("parent_id",),
        unique_constraints=(UniqueConstraint(("value",)),) if include_unique else (),
        checks=(CheckConstraint(check_expression),),
        indexes=(Index(index_name, ("value",)),),
    )
    child = Table(
        name="children",
        columns=(
            Column("child_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
            Column("parent_id", "TEXT", ColumnGroup.REFERENCE, nullable=False),
        ),
        primary_key=("child_id",),
        foreign_keys=(
            ForeignKey(
                ("parent_id",),
                "parents",
                ("parent_id",),
                on_delete=on_delete,
            ),
        ),
    )
    return Database(name="contract.db", tables=(parent, child))


def test_generated_tables_do_not_name_primary_foreign_unique_or_check_constraints():
    for database in DATABASE_SCHEMAS:
        for table in database.tables:
            assert "CONSTRAINT " not in table.create_table_sql()


def test_database_validation_ignores_optional_constraint_labels(tmp_path):
    database = _validation_contract()
    path = tmp_path / database.name
    with sqlite3.connect(path) as connection:
        parent_sql = database.tables[0].create_table_sql()
        parent_sql = parent_sql.replace(
            "PRIMARY KEY", "CONSTRAINT first_primary_label PRIMARY KEY"
        ).replace("UNIQUE", "CONSTRAINT another_unique_label UNIQUE").replace(
            "CHECK", "CONSTRAINT readable_check_label CHECK"
        )
        child_sql = database.tables[1].create_table_sql()
        child_sql = child_sql.replace(
            "PRIMARY KEY", "CONSTRAINT child_primary_label PRIMARY KEY"
        ).replace("FOREIGN KEY", "CONSTRAINT parent_link_label FOREIGN KEY")
        connection.execute(parent_sql)
        connection.execute(child_sql)
        for table in database.tables:
            for statement in table.create_index_sql():
                connection.execute(statement)

    assert database.validate_existing(path)


@pytest.mark.parametrize(
    "changed_database",
    (
        _validation_contract(value_default="'pending'"),
        _validation_contract(include_unique=False),
        _validation_contract(check_expression="length(value) >= 0"),
        _validation_contract(on_delete="RESTRICT"),
        _validation_contract(index_name="a_different_index_name"),
    ),
)
def test_database_validation_still_rejects_changed_rules(tmp_path, changed_database):
    expected_database = _validation_contract()
    path = tmp_path / expected_database.name
    with sqlite3.connect(path) as connection:
        changed_database.create(connection)

    with pytest.raises(UnsupportedSchemaError):
        expected_database.validate_existing(path)


def test_index_names_only_need_to_be_legal_and_unique():
    database = _validation_contract(index_name="records_by_value")
    assert database.tables[0].indexes[0].name == "records_by_value"

    duplicate_index = Index("same_lookup", ("value",))
    with pytest.raises(ValueError, match="duplicate explicit indexes"):
        Database(
            name="duplicates.db",
            tables=(
                Table(
                    name="first_records",
                    columns=(Column("value", "TEXT", ColumnGroup.PRIMARY_KEY),),
                    primary_key=("value",),
                    indexes=(duplicate_index,),
                ),
                Table(
                    name="second_records",
                    columns=(Column("value", "TEXT", ColumnGroup.PRIMARY_KEY),),
                    primary_key=("value",),
                    indexes=(duplicate_index,),
                ),
            ),
        )


@pytest.mark.parametrize(
    "database_name",
    ("Settings.db", "settings-db", "settings.sqlite", "settings..db"),
)
def test_database_names_require_lowercase_snake_case(database_name):
    with pytest.raises(ValueError, match="lowercase snake_case"):
        Database(name=database_name, tables=())


def test_web_access_settings_rejects_an_unknown_provider(tmp_path):
    path = tmp_path / CONFIG_DATABASE_SCHEMA.name
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        CONFIG_DATABASE_SCHEMA.create(connection)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO web_access_settings "
                "(singleton_id, active_provider_id, is_enabled) "
                "VALUES (1, 'missing', 1)"
            )


@pytest.mark.parametrize(
    ("table_name", "columns", "values"),
    (
        (
            "lab_test_report",
            "report_id, item_id, member_id, category_name, item_name_zh, result_text",
            "'report-1', 'item-1', 'member-2', 'category-1', '项目', '结果'",
        ),
        (
            "examination_report",
            "report_id, member_id, exam_name",
            "'report-1', 'member-2', '检查'",
        ),
        (
            "pathology_report",
            "report_id, member_id",
            "'report-1', 'member-2'",
        ),
        (
            "surgery_report",
            "report_id, member_id",
            "'report-1', 'member-2'",
        ),
        (
            "other_report",
            "report_id, member_id, report_body",
            "'report-1', 'member-2', '正文'",
        ),
    ),
)
def test_report_detail_tables_reject_a_different_member(
    tmp_path,
    table_name,
    columns,
    values,
):
    path = tmp_path / REPORT_DATABASE_SCHEMA.name
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        REPORT_DATABASE_SCHEMA.create(connection)
        connection.execute(
            "INSERT INTO reports "
            "(report_id, member_id, report_type, report_name, report_time, "
            "created_at, updated_at) VALUES "
            "('report-1', 'member-1', '其它报告', '报告', '2026-01-01', "
            "'2026-01-01', '2026-01-01')"
        )
        if table_name == "lab_test_report":
            connection.execute(
                "INSERT INTO lab_items (item_id, item_name_zh) "
                "VALUES ('item-1', '项目')"
            )
            connection.execute(
                "INSERT INTO lab_categories (category_name) VALUES ('category-1')"
            )
            connection.execute(
                "INSERT INTO lab_item_category_links (item_id, category_name, is_primary) "
                "VALUES ('item-1', 'category-1', 1)"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                f"INSERT INTO {table_name} ({columns}) VALUES ({values})"
            )


def test_table_contract_rejects_a_primary_key_after_data_columns():
    with pytest.raises(ValueError, match="canonical column order"):
        Table(
            name="invalid_order",
            columns=(
                Column("payload", "TEXT", ColumnGroup.DATA),
                Column("record_id", "TEXT", ColumnGroup.PRIMARY_KEY),
            ),
            primary_key=("record_id",),
        )


ACCOUNT_ID = "00000000-0000-4000-8000-000000000001"

def test_first_use_configuration_initialization_is_atomic_and_serialized(monkeypatch):
    schema_started = Event()
    finish_schema = Event()
    second_started = Event()
    original = config_database.create_models_table_sql

    def paused_schema():
        schema_started.set()
        assert finish_schema.wait(timeout=5)
        return original()

    def initialize_again():
        second_started.set()
        config_database.initialize_config_database(ACCOUNT_ID)

    monkeypatch.setattr(config_database, "create_models_table_sql", paused_schema)
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(config_database.initialize_config_database, ACCOUNT_ID)
        try:
            assert schema_started.wait(timeout=5)
            second = executor.submit(initialize_again)
            assert second_started.wait(timeout=5)
            with pytest.raises(TimeoutError):
                second.result(timeout=0.1)
            with sqlite3.connect(app_paths().config_db(ACCOUNT_ID)) as connection:
                assert connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall() == []
        finally:
            finish_schema.set()
        first.result(timeout=5)
        second.result(timeout=5)

    config_database._validate_existing_config(ACCOUNT_ID)


@pytest.mark.parametrize("database,damage", [
    pytest.param(db, damage, id=f"{db.name}-{damage}")
    for db in DATABASE_SCHEMAS
    for damage in ("missing_table", "extra_table", "renamed_column", "extra_column")
    # An empty database is a supported initialization state; only partial schemas are damaged.
    if damage != "missing_table" or len(db.tables) > 1
])
def test_database_rejects_structural_damage_without_writing(tmp_path, database, damage):
    path = tmp_path / database.name
    table = database.tables[0]
    with sqlite3.connect(path) as connection:
        database.create(connection)
        if damage == "missing_table":
            connection.execute(f'DROP TABLE "{table.name}"')
        elif damage == "extra_table":
            connection.execute('CREATE TABLE unexpected_table (value TEXT)')
        elif damage == "renamed_column":
            connection.execute(f'ALTER TABLE "{table.name}" RENAME COLUMN "{table.column_names[0]}" TO unexpected_column')
        else:
            connection.execute(f'ALTER TABLE "{table.name}" ADD COLUMN unexpected_column TEXT')
    before = path.read_bytes()
    with pytest.raises(UnsupportedSchemaError):
        database.validate_existing(path)
    assert path.read_bytes() == before


def test_typed_report_fields_match_their_storage_columns():
    from backend.app.schemas.report import REPORT_STRUCTURES

    tables = {table.name: table for table in REPORT_DATABASE_SCHEMA.tables}
    for table_name, model in REPORT_STRUCTURES.values():
        assert set(tables[table_name].column_names) - {"member_id", "report_id"} == set(model.model_fields)
