"""experiment_runs: relevant_criteria (JSON), answer_source (String 16), both nullable. Idempotent.

Older rows keep NULL; load_record falls back to the answer_source stored in config."""
import sqlalchemy as sa
from alembic import op

revision = "0012_experiment_run_fields"
down_revision = "0011_experiments"
branch_labels = None
depends_on = None

COLUMNS = {"relevant_criteria": sa.JSON(), "answer_source": sa.String(16)}


def _columns() -> set[str] | None:
    insp = sa.inspect(op.get_bind())
    if "experiment_runs" not in insp.get_table_names():
        return None
    return {c["name"] for c in insp.get_columns("experiment_runs")}


def upgrade():
    cols = _columns()
    if cols is None:
        return
    for name, type_ in COLUMNS.items():
        if name not in cols:
            op.add_column("experiment_runs", sa.Column(name, type_, nullable=True))


def _answer_source_back_to_config() -> None:
    """Keep provenance: before the column is dropped, copy answer_source into config["answer_source"]
    (the pre-0012 storage that load_record still reads)."""
    bind = op.get_bind()
    runs = sa.table("experiment_runs", sa.column("id", sa.String), sa.column("config", sa.JSON),
                    sa.column("answer_source", sa.String))
    rows = bind.execute(sa.select(runs.c.id, runs.c.config, runs.c.answer_source)
                        .where(runs.c.answer_source.isnot(None))).all()
    for rid, config, source in rows:
        config = dict(config or {})
        config["answer_source"] = source
        bind.execute(runs.update().where(runs.c.id == rid).values(config=config))


def downgrade():
    cols = _columns()
    if cols is None:
        return
    if "answer_source" in cols:
        _answer_source_back_to_config()
    drop = [n for n in COLUMNS if n in cols]
    if drop:
        with op.batch_alter_table("experiment_runs") as batch:
            for name in drop:
                batch.drop_column(name)
