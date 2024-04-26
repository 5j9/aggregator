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
    main_url: str
    url: str
    title: str

    def __str__(self) -> str:
        # language=html
        return f"""\
            <div class="item">
                <a href="{self.url}">{self.title}</a>
                <div class='main_url'>{self.main_url}</div>
                <button 
                    hx-get="/mark_as_read?url={quote_plus(self.url)}" 
                    hx-swap="delete"
                    hx-target="closest .item"
                    hx-disabled-elt="this">mark as read</button>
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
    main_url: str = sub.url

    body = await sub.body
    if body is None:
        return

    try:
        await sub.select()
    except Exception as e:
        logger.error(f'{e!r} on {main_url}')
        return

    links = sub.links
    if not links:
        logger.warning(f'no links match on {main_url=}')
        return

    titles = sub.titles
    if len(links) != len(titles):
        logger.error(f'len(links) != len(titles) on {main_url=}')
        return

    # convert relative links to absolute
    urls = tuple(urljoin(main_url, link) for link in links)

    # delete old urls that no longer exist on subscription page
    cur.execute(
        f'DELETE FROM state WHERE source_url = ? AND item_url NOT IN {urls}',
        (main_url,),
    )

    already_read = cur.execute(
        'SELECT item_url FROM state '
        'WHERE source_url = ? AND read_timestamp IS NOT NULL',
        (main_url,),
    ).fetchall()
    already_read = set(t[0] for t in already_read)

    items = []
    for url, title in zip(urls, titles):
        if url in already_read:
            continue
        items.append(Item(main_url, url, title.strip()))

    # IGNORE is needed in case multiple tabs run this function concurrently
    cur.executemany(
        'INSERT OR IGNORE INTO state (source_url, item_url, title, read_timestamp) '
        'VALUES (?, ?, ?, Null);',
        ((item.main_url, item.url, item.title) for item in items),
    )
    if items:
        logger.debug('found new items on %s', main_url)
    else:
        logger.debug('no new items on %s', main_url)
    return items


async def check_all() -> Generator[list[Item], None, None]:
    for c in as_completed([check(sub) for sub in SUBS]):
        items: list[Item] | None = await c
        if items is not None:
            yield items
