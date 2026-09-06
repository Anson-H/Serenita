from backend.app.storage.schema import (
    CheckConstraint,
    Column,
    ColumnGroup,
    Database,
    ForeignKey,
    Index,
    STORED_FILE_DATA_COLUMNS,
    Table,
    UniqueConstraint,
)


REPORT_DATABASE_SCHEMA = Database(
    name="reports.db",
    tables=(
        Table(
            name="reports",
            columns=(
                Column("report_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column("report_type", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("report_name", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("report_time", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("institution_name", "TEXT", ColumnGroup.DATA),
                Column(
                    "analysis_content",
                    "TEXT",
                    ColumnGroup.DATA,
                    nullable=False,
                    default="''",
                ),
                Column(
                    "analysis_outdated",
                    "INTEGER",
                    ColumnGroup.STATE,
                    nullable=False,
                    default="0",
                ),
                Column("analysis_updated_at", "TEXT", ColumnGroup.STATE),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
                Column("updated_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("report_id",),
            unique_constraints=(
                UniqueConstraint(
                    ("report_id", "member_id"),
                ),
            ),
            checks=(
                CheckConstraint(
                    "report_type IN ('检验报告', '检查报告', '病理报告', "
                    "'手术报告', '其它报告')",
                ),
                CheckConstraint(
                    "analysis_outdated IN (0, 1)",
                ),
            ),
            indexes=(
                Index(
                    "idx_reports__member_time",
                    ("member_id", "report_time"),
                ),
                Index(
                    "idx_reports__member_type_time",
                    ("member_id", "report_type", "report_time"),
                ),
            ),
        ),
        Table(
            name="report_sources",
            columns=(
                Column("resource_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                *STORED_FILE_DATA_COLUMNS,
                Column(
                    "source_kind",
                    "TEXT",
                    ColumnGroup.DATA,
                    nullable=False,
                    default="'unknown'",
                ),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("resource_id",),
            unique_constraints=(
                UniqueConstraint(
                    ("resource_id", "member_id"),
                ),
            ),
            checks=(
                CheckConstraint(
                    "size_bytes >= 0",
                ),
                CheckConstraint(
                    "source_kind IN ('screenshot', 'scan', 'pdf', 'photo', 'unknown')",
                ),
            ),
            indexes=(
                Index(
                    "idx_report_sources__member_sha256",
                    ("member_id", "sha256"),
                ),
            ),
        ),
        Table(
            name="report_source_links",
            columns=(
                Column("report_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("resource_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column(
                    "is_primary",
                    "INTEGER",
                    ColumnGroup.STATE,
                    nullable=False,
                ),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("report_id", "resource_id"),
            foreign_keys=(
                ForeignKey(
                    ("report_id", "member_id"),
                    "reports",
                    ("report_id", "member_id"),
                    on_delete="CASCADE",
                ),
                ForeignKey(
                    ("resource_id", "member_id"),
                    "report_sources",
                    ("resource_id", "member_id"),
                    on_delete="CASCADE",
                ),
            ),
            checks=(
                CheckConstraint(
                    "is_primary IN (0, 1)",
                ),
            ),
            indexes=(
                Index(
                    "idx_report_source_links__member_resource",
                    ("member_id", "resource_id"),
                ),
                Index(
                    "idx_report_source_links__member_report",
                    ("member_id", "report_id"),
                ),
            ),
        ),
        Table(
            name="report_source_file_cleanup_outbox",
            columns=(
                Column("cleanup_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column("relative_path", "TEXT", ColumnGroup.DATA, nullable=False),
                Column(
                    "attempt_count",
                    "INTEGER",
                    ColumnGroup.STATE,
                    nullable=False,
                    default="0",
                ),
                Column("last_attempt_at", "TEXT", ColumnGroup.STATE),
                Column("created_at", "TEXT", ColumnGroup.AUDIT, nullable=False),
            ),
            primary_key=("cleanup_id",),
            unique_constraints=(
                UniqueConstraint(
                    ("member_id", "relative_path"),
                ),
            ),
            checks=(
                CheckConstraint(
                    "attempt_count >= 0",
                ),
            ),
            indexes=(
                Index(
                    "idx_report_source_file_cleanup_outbox__member_created_at",
                    ("member_id", "created_at"),
                ),
            ),
        ),
        Table(
            name="lab_items",
            columns=(
                Column("item_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("item_name_zh", "TEXT", ColumnGroup.DATA, nullable=False),
                Column(
                    "aliases", "TEXT", ColumnGroup.DATA, nullable=False, default="'[]'"
                ),
                Column("description", "TEXT", ColumnGroup.DATA),
            ),
            primary_key=("item_id",),
            indexes=(Index("idx_lab_items__item_name_zh", ("item_name_zh",)),),
        ),
        Table(
            name="lab_categories",
            columns=(
                Column(
                    "category_name", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False
                ),
                Column("description", "TEXT", ColumnGroup.DATA),
            ),
            primary_key=("category_name",),
        ),
        Table(
            name="lab_item_category_links",
            columns=(
                Column("item_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column(
                    "category_name", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False
                ),
                Column("is_primary", "INTEGER", ColumnGroup.STATE, nullable=False),
            ),
            primary_key=("item_id", "category_name"),
            foreign_keys=(
                ForeignKey(
                    ("item_id",),
                    "lab_items",
                    ("item_id",),
                    on_delete="CASCADE",
                ),
                ForeignKey(
                    ("category_name",),
                    "lab_categories",
                    ("category_name",),
                    on_update="CASCADE",
                    on_delete="CASCADE",
                ),
            ),
            checks=(
                CheckConstraint(
                    "is_primary IN (0, 1)",
                ),
            ),
            indexes=(
                Index(
                    "uidx_lab_item_category_links__primary_item",
                    ("item_id",),
                    unique=True,
                    where="is_primary = 1",
                ),
            ),
        ),
        Table(
            name="lab_test_report",
            columns=(
                Column("report_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("item_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column("category_name", "TEXT", ColumnGroup.REFERENCE, nullable=False),
                Column("item_name_zh", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("result_text", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("reference_text", "TEXT", ColumnGroup.DATA),
                Column(
                    "flag_text",
                    "TEXT",
                    ColumnGroup.STATE,
                    nullable=False,
                    default="'未标记'",
                ),
            ),
            primary_key=("report_id", "item_id"),
            foreign_keys=(
                ForeignKey(
                    ("report_id", "member_id"),
                    "reports",
                    ("report_id", "member_id"),
                    on_delete="CASCADE",
                ),
                ForeignKey(
                    ("item_id", "category_name"),
                    "lab_item_category_links",
                    ("item_id", "category_name"),
                    on_update="CASCADE",
                    on_delete="CASCADE",
                ),
            ),
            checks=(
                CheckConstraint(
                    "flag_text IN ('未标记', '正常', '异常', '偏高', '偏低')",
                ),
            ),
        ),
        Table(
            name="examination_report",
            columns=(
                Column("report_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column("exam_name", "TEXT", ColumnGroup.DATA, nullable=False),
                Column("clinical_diagnosis", "TEXT", ColumnGroup.DATA),
                Column("exam_method", "TEXT", ColumnGroup.DATA),
                Column("exam_findings", "TEXT", ColumnGroup.DATA),
                Column("exam_diagnosis", "TEXT", ColumnGroup.DATA),
            ),
            primary_key=("report_id",),
            foreign_keys=(
                ForeignKey(
                    ("report_id", "member_id"),
                    "reports",
                    ("report_id", "member_id"),
                    on_delete="CASCADE",
                ),
            ),
            indexes=(
                Index(
                    "idx_examination_report__member_exam_name",
                    ("member_id", "exam_name"),
                ),
            ),
        ),
        Table(
            name="pathology_report",
            columns=(
                Column("report_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column("submitted_specimen", "TEXT", ColumnGroup.DATA),
                Column("gross_examination", "TEXT", ColumnGroup.DATA),
                Column("diagnosis", "TEXT", ColumnGroup.DATA),
                Column("sampling_location", "TEXT", ColumnGroup.DATA),
            ),
            primary_key=("report_id",),
            foreign_keys=(
                ForeignKey(
                    ("report_id", "member_id"),
                    "reports",
                    ("report_id", "member_id"),
                    on_delete="CASCADE",
                ),
            ),
            indexes=(
                Index(
                    "idx_pathology_report__member_report",
                    ("member_id", "report_id"),
                ),
            ),
        ),
        Table(
            name="surgery_report",
            columns=(
                Column("report_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column("preoperative_diagnosis", "TEXT", ColumnGroup.DATA),
                Column("intraoperative_diagnosis", "TEXT", ColumnGroup.DATA),
                Column("anesthesia_method", "TEXT", ColumnGroup.DATA),
                Column("started_at", "TEXT", ColumnGroup.DATA),
                Column("ended_at", "TEXT", ColumnGroup.DATA),
                Column("blood_transfusion", "TEXT", ColumnGroup.DATA),
                Column("intraoperative_blood_loss", "TEXT", ColumnGroup.DATA),
                Column("intraoperative_urine_output", "TEXT", ColumnGroup.DATA),
                Column("intraoperative_transfusion", "TEXT", ColumnGroup.DATA),
                Column("intraoperative_infusion", "TEXT", ColumnGroup.DATA),
                Column("intraoperative_other_drugs", "TEXT", ColumnGroup.DATA),
                Column("procedure_description", "TEXT", ColumnGroup.DATA),
                Column("postoperative_vital_signs", "TEXT", ColumnGroup.DATA),
            ),
            primary_key=("report_id",),
            foreign_keys=(
                ForeignKey(
                    ("report_id", "member_id"),
                    "reports",
                    ("report_id", "member_id"),
                    on_delete="CASCADE",
                ),
            ),
            indexes=(
                Index(
                    "idx_surgery_report__member_started_ended",
                    ("member_id", "started_at", "ended_at"),
                ),
            ),
        ),
        Table(
            name="other_report",
            columns=(
                Column("report_id", "TEXT", ColumnGroup.PRIMARY_KEY, nullable=False),
                Column("member_id", "TEXT", ColumnGroup.SCOPE, nullable=False),
                Column("report_body", "TEXT", ColumnGroup.DATA, nullable=False),
            ),
            primary_key=("report_id",),
            foreign_keys=(
                ForeignKey(
                    ("report_id", "member_id"),
                    "reports",
                    ("report_id", "member_id"),
                    on_delete="CASCADE",
                ),
            ),
            indexes=(
                Index(
                    "idx_other_report__member_report",
                    ("member_id", "report_id"),
                ),
            ),
        ),
    ),
)
