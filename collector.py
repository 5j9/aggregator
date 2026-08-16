import importlib.util
import os
import sys
from asyncio import as_completed
from collections.abc import AsyncGenerator
from pprint import pformat

from base import Item, Subscription, con, cur, logger


def import_subscriptions():
    """Import subscriptions module from OneDrive"""
    # Get OneDrive path
    onedrive_path = os.environ.get('OneDrive')
    if onedrive_path is None:
        raise OSError('OneDrive environment variable not set')

    file_path = os.path.join(onedrive_path, 'subscriptions.py')
    spec = importlib.util.spec_from_file_location('subscriptions', file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f'Could not load spec for: {file_path}')

    subscriptions = importlib.util.module_from_spec(spec)
    sys.modules['subscriptions'] = subscriptions
    spec.loader.exec_module(subscriptions)

    return subscriptions


import_subscriptions()

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
    db_urls = {
        t[0]
        for t in cur.execute(
            'SELECT DISTINCT source_url FROM state'
        ).fetchall()
    }
    unsubscribed_urls = db_urls - sub_urls
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
