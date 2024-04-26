import sys
from asyncio import as_completed
from collections.abc import Generator
from dataclasses import dataclass
from urllib.parse import quote_plus, urljoin

# import subscriptions to fill Subscription.__subclassess__
import subscriptions  # noqa
from base import Subscription, con, cur, logger

SUBS = [s() for s in Subscription.__subclasses__()]


def show_exception_and_confirm_exit(exc_type, exc_value, tb):
    import traceback

    traceback.print_exception(exc_type, exc_value, tb)
    con.close()
    input('Press enter to exit.')
    raise SystemExit


sys.excepthook = show_exception_and_confirm_exit


@dataclass(slots=True)
class Item:
    source_url: str
    url: str
    title: str
    read_timestamp: str = None

    def __str__(self) -> str:
        if self.read_timestamp is None:
            # language=html
            return f"""\
                <div class="item">
                    <a href="{self.url}">{self.title}</a>
                    <div>{self.source_url}</div>
                    <button 
                        hx-get="/mark_as_read?url={quote_plus(self.url)}" 
                        hx-swap="delete"
                        hx-target="closest .item"
                        hx-disabled-elt="this">mark as read</button>
                </div>
            """
        return f"""\
            <div class="item">
                <a href="{self.url}">{self.title}</a>
                <div>{self.source_url}</div>
                <div>{self.read_timestamp}</div>
            </div>
        """


def sync_db_with_subscriptions():
    subs_urls = {sub.url for sub in SUBS}
    unsubscribed_urls = (
        set(
            t[0]
            for t in cur.execute(
                'SELECT DISTINCT source_url FROM state'
            ).fetchall()
        )
        - subs_urls
    )
    if not unsubscribed_urls:
        return
    logger.info(
        'deleting %d unsubscribed urls from state.db: %s',
        len(unsubscribed_urls),
        unsubscribed_urls,
    )
    cur.executemany(
        'DELETE FROM state WHERE source_url=?',
        ((url,) for url in unsubscribed_urls),
    )


sync_db_with_subscriptions()


async def check(sub: Subscription) -> list[Item] | None:
    source_url: str = sub.url

    body = await sub.body
    if body is None:
        return

    try:
        await sub.select()
    except Exception as e:
        logger.error(f'{e!r} on {source_url}')
        return

    links = sub.links
    if not links:
        logger.warning(f'no links match on {source_url=}')
        return

    titles = sub.titles
    if len(links) != len(titles):
        logger.error(f'len(links) != len(titles) on {source_url=}')
        return

    # convert relative links to absolute
    urls = tuple(urljoin(source_url, link) for link in links)

    # delete old urls that no longer exist on subscription page
    cur.execute(
        f'DELETE FROM state WHERE source_url = ? AND item_url NOT IN {urls}',
        (source_url,),
    )

    already_read = cur.execute(
        'SELECT item_url FROM state '
        'WHERE source_url = ? AND read_timestamp IS NOT NULL',
        (source_url,),
    ).fetchall()
    already_read = set(t[0] for t in already_read)

    items = []
    for url, title in zip(urls, titles):
        if url in already_read:
            continue
        items.append(Item(source_url, url, title.strip()))

    # IGNORE is needed in case multiple tabs run this function concurrently
    cur.executemany(
        'INSERT OR IGNORE INTO state (source_url, item_url, title, read_timestamp) '
        'VALUES (?, ?, ?, Null);',
        ((item.source_url, item.url, item.title) for item in items),
    )
    if items:
        logger.debug('found new items on %s', source_url)
    else:
        logger.debug('no new items on %s', source_url)
    return items


async def check_all() -> Generator[list[Item], None, None]:
    for c in as_completed([check(sub) for sub in SUBS]):
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
