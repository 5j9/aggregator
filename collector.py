import sys
from asyncio import as_completed
from collections.abc import AsyncGenerator
from pprint import pformat

# import subscriptions to fill Subscription.__subclassess__
from base import Item, Subscription, con, cur, logger

SUBS = [s() for s in Subscription.__subclasses__()]


def show_exception_and_confirm_exit(exc_type, exc_value, tb):
    import traceback

    traceback.print_exception(exc_type, exc_value, tb)
    con.close()
    input('Press enter to exit.')
    raise SystemExit


sys.excepthook = show_exception_and_confirm_exit


def sync_db_with_subscriptions():
    sub_urls = {sub.url for sub in SUBS}
    unsubscribed_urls = (
        set(
            t[0]
            for t in cur.execute(
                'SELECT DISTINCT source_url FROM state'
            ).fetchall()
        )
        - sub_urls
    )
    if not unsubscribed_urls:
        return
    logger.info(
        'deleting %d unsubscribed urls from check_state.sqlite3:\n%s',
        len(unsubscribed_urls),
        pformat(unsubscribed_urls),
    )
    cur.executemany(
        'DELETE FROM state WHERE source_url=?',
        ((url,) for url in unsubscribed_urls),
    )


sync_db_with_subscriptions()


async def check_all() -> AsyncGenerator[list[Item], None]:
    for c in as_completed([sub.check() for sub in SUBS]):
        items: list[Item] | None = await c
        if items is not None:
            yield items


def recently_read_items(limit: int, source_url=None) -> list[Item]:
    src_cond = (
        f'source_url = {source_url} AND ' if source_url is not None else ''
    )
    results = cur.execute(
        'SELECT source_url, item_url, title, read_timestamp FROM state '
        f'WHERE {src_cond} read_timestamp IS NOT NULL '
        f'ORDER BY read_timestamp DESC '
        f'LIMIT ?',
        (limit,),
    ).fetchall()
    return [
        Item(source_url, url, title, read_timestamp)
        for source_url, url, title, read_timestamp in results
    ]
