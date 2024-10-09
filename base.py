import logging
import os
import sqlite3
from abc import abstractmethod
from functools import partial
from json import loads
from pathlib import Path

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
        '%(pathname)s:%(lineno)d %(levelname)s %(message)s'
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


parse_html = partial(fromstring, parser=HTMLParser(encoding='utf8'))
parse_xml = fromstring


def parse(doctype, body):
    if doctype == 'xml':
        return parse_xml(body)
    return parse_html(body)


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
