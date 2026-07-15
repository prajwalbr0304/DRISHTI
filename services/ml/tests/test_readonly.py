"""Read-only role tests: the restricted layer can SELECT but must reject DML."""
import psycopg2
import pytest

from app import db
from conftest import requires_db


@requires_db
def test_readonly_can_select():
    with db.ro_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_user")
            assert cur.fetchone()[0] == db.get_settings().readonly_role
            cur.execute('SELECT COUNT(*) FROM "CaseMaster"')
            assert cur.fetchone()[0] >= 0


@requires_db
def test_readonly_blocks_insert():
    with pytest.raises(psycopg2.Error) as exc:
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO "State" ("StateName") VALUES (%s)',
                    ("__should_not_persist__",),
                )
    # Either the read-only transaction or the missing privilege rejects it.
    msg = str(exc.value).lower()
    assert "read-only" in msg or "permission denied" in msg


@requires_db
def test_readonly_blocks_update():
    with pytest.raises(psycopg2.Error):
        with db.ro_conn() as conn:
            with conn.cursor() as cur:
                cur.execute('UPDATE "State" SET "StateName"=\'x\' WHERE "StateID"=-1')


@requires_db
def test_no_row_leaked_from_blocked_insert():
    # Prove the blocked INSERT above did not persist anything.
    with db.rw_conn() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM "State" WHERE "StateName"=%s',
                        ("__should_not_persist__",))
            assert cur.fetchone()[0] == 0
