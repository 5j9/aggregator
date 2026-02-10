import logging
import os
import sqlite3
from abc import abstractmethod
from dataclasses import dataclass
from functools import partial
from json import loads
from pathlib import Path
from urllib.parse import quote_plus, urljoin

from aiohttp import ClientTimeout
from aiohutils.session import SessionManager
from lxml.etree import HTMLParser, fromstring

PROJECT = Path(__file__).parent


def get_logger():
    logger = logging.getLogger(__name__)
    level = os.getenv('LOGLEVEL', 'INFO').upper()
    logger.setLevel(level)
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    formatter = logging.Formatter(
        '%(levelname)s %(pathname)s:%(lineno)d\n%(message)s'
    )
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


logger = get_logger()

con = sqlite3.connect(PROJECT / 'check_state.sqlite3')

cur = con.cursor()
cur.execute(
    'CREATE TABLE IF NOT EXISTS state (source_url, item_url TEXT PRIMARY KEY, title, read_timestamp);'
)

session_manager = SessionManager(timeout=ClientTimeout(30))


async def read(url, method='GET', **kwargs):
    try:
        response = await session_manager.request(url, **kwargs)
        return await response.read()
    except Exception as e:
        logger.error(f'{e!r} on {url}')
        return


parse_html = partial(fromstring, parser=HTMLParser(encoding='utf8'))
parse_xml = fromstring


def parse(doctype, body):
    if doctype == 'xml':
        return parse_xml(body)
    return parse_html(body)


@dataclass(slots=True)
class Item:
    source_url: str
    url: str
    title: str
    read_timestamp: str | None = None

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


class Subscription:
    url: str
    name: str
    method: str = 'GET'
    ssl: bool | None = None
    doctype = 'html'
    json_payload = None
    _body: bytes | None = None

    @property
    async def body(self):
        if self._body is not None:
            return self._body
        body = await read(
            self.url, ssl=self.ssl, json=self.json_payload, method=self.method
        )
        if body is None:
            logger.error('body is None for %s', self.url)
            return None
        self._body = body
        return body

    @property
    async def json(self):
        body = await self.body
        if body is None:
            return None
        return loads(body)

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
        self.links = []
        self.titles = []

    async def check(self) -> list[Item] | None:
        source_url: str = self.url

        body = await self.body
        if body is None:
            return

        try:
            await self.select()
        except Exception as e:
            logger.error(f'{e!r} on {source_url}')
            return

        links = self.links
        if not links:
            logger.warning(f'no links match on {source_url=}')
            return

        titles = self.titles
        if len(links) != len(titles):
            logger.error(f'len(links) != len(titles) on {source_url=}')
            return

        # convert relative links to absolute
        urls = [urljoin(source_url, link) for link in links]

        # delete old urls that no longer exist on subscription page
        cur.execute(
            f'DELETE FROM state '
            f'WHERE source_url = ? '
            f'AND item_url NOT IN ({", ".join("?" * len(urls))})',
            (source_url, *urls),
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
