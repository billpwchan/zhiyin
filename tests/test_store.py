import concurrent.futures as cf

from zhiyin import store


def test_fresh_database_survives_concurrent_first_use():
    def write(i):
        con = store.db()
        con.execute("insert or replace into kv values (?, ?)", (f"k{i}", "1"))
        con.commit()
        return True

    with cf.ThreadPoolExecutor(16) as ex:
        assert all(ex.map(write, range(64)))
    assert store.db().execute("pragma journal_mode").fetchone()[0] == "wal"


def test_the_old_second_account_flag_is_dropped():
    con = store.db()
    con.execute("alter table users add column mine integer not null default 0")
    con.execute("insert into users(id, name, created, status, email, mine) values ('u2nd', '我的另一个账号', 0, 'ready', 'b@example.com', 1)")
    store._migrate(con)
    assert "mine" not in {r[1] for r in con.execute("pragma table_info(users)")}
    assert con.execute("select name from users where id='u2nd'").fetchone()[0] == "b@example.com"
