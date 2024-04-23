import sqlite3
import sys
from abc import abstractmethod
from asyncio import as_completed
from functools import partial
from json import loads
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from aiohttp import ClientTimeout
from aiohutils.session import SessionManager
from lxml.etree import HTMLParser, fromstring

PROJECT = Path(__file__).parent
con = sqlite3.connect(PROJECT / 'check_state.db')
cur = con.cursor()
cur.execute(
    'CREATE TABLE IF NOT EXISTS state (source_url, item_url, read_timestamp);'
)


class Subscription:
    url: str
    name: str
    method: str = 'GET'
    ssl: bool = None
    doctype = 'html'
    json_payload = None
    _body: bytes = None

    @property
    async def body(self):
        if self._body is not None:
            return self._body
        body = await read(
            self.url, ssl=self.ssl, json=self.json_payload, method=self.method
        )
        if body is None:
            logger.error('body is None for %s', self.url)
            return
        self._body = body
        return body

    @property
    async def json(self):
        return loads(await self.body)

    @property
    async def parsed(self):
        body = await self.body
        return parse(self.doctype, body)

    @property
    async def xpath(
        self,
    ):
        return (await self.parsed).xpath

    @property
    async def cssselect(
        self,
    ):
        return (await self.parsed).cssselect

    @abstractmethod
    async def select(self) -> None:
        self.links = [...]
        self.titles = [...]


# import subscriptions to fill Subscription.__subclassess__
import subscriptions  # noqa

SUBS = [s() for s in Subscription.__subclasses__()]


def get_logger():
    import logging

    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(pathname)s:%(lineno)d %(levelname)s %(message)s'
    )
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


logger = get_logger()


def show_exception_and_confirm_exit(exc_type, exc_value, tb):
    import traceback

    traceback.print_exception(exc_type, exc_value, tb)
    input('Press enter to exit.')
    raise SystemExit


# language=html
item_template = """\
<div class="item">
    <a href="{url}">{title}</a>
    <div class='main_url'>{main_url}</div>
    <button hx-get="/mark_as_read?main_url={qmain_url}&url={qurl}" hx-swap="delete" hx-target="closest .item">mark as read</button>
</div>
"""


def create_item(url: str, title: str, main_url: str) -> str:
    return item_template.format(
        url=url,
        qurl=quote_plus(url),
        main_url=main_url,
        qmain_url=quote_plus(main_url),
        title=title,
    )


sys.excepthook = show_exception_and_confirm_exit


# SLUG = str.maketrans(r'\/:*?"<>|', '-' * 9)
INBOX = PROJECT / 'inbox'

parse_html = partial(fromstring, parser=HTMLParser(encoding='utf8'))
parse_xml = fromstring


def sync_db_with_subscriptions():
    subs_urls = {sub.url for sub in SUBS}
    last_checked_urls = cur.execute('SELECT DISTINCT source_url FROM state')
    unsubscribed_urls = set(last_checked_urls) - subs_urls
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


session_manager = SessionManager(timeout=ClientTimeout(30))


async def read(url, method='GET', **kwargs):
    if method == 'GET':
        request = session_manager.get
    else:
        request = session_manager.session.post
    try:
        response = await request(url, **kwargs)
        return await response.read()
    except Exception as e:
        logger.error(f'{e!r} on {url}')
        return


def parse(doctype, body):
    if doctype == 'xml':
        return parse_xml(body)
    return parse_html(body)


async def check(sub: Subscription):
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

    # delete old urls that no longer exist
    cur.execute(
        f'DELETE FROM state WHERE source_url = {main_url} AND item_url NOT IN {urls}'
    )

    already_read = cur.execute(
        f'SELECT item_url, read_timestamp FROM state WHERE source_url = {main_url}'
    ).fetchall()
    already_read = dict(already_read)

    items = []
    for url, title in zip(urls, titles):
        if already_read.get(url) is not None:
            break
        items.append(create_item(url, title.strip(), main_url))

    if items:
        logger.debug('found new items on %s', main_url)
    else:
        logger.debug('no new items on %s', main_url)
    return items


async def check_all():
    for c in as_completed([check(sub) for sub in SUBS]):
        items = await c
        if items is not None:
            yield items
