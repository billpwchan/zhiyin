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
