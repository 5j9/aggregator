import sys
from abc import abstractmethod
from asyncio import as_completed
from functools import partial
from json import dumps, loads
from urllib.parse import quote_plus, urljoin

from aiohttp import ClientTimeout
from aiohutils.session import SessionManager
from lxml.etree import HTMLParser, fromstring
from path import Path


class Subscription:
    url: str
    ssl: bool = None
    doctype = 'html'

    @property
    async def body(self):
        body = await read(self.url, self.ssl)
        if body is None:
            logger.error('body is None for %s', self.url)
            return
        return body

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
    logger.setLevel(logging.DEBUG)
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
    input("Press enter to exit.")
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

PROJECT = Path(__file__).parent
INBOX = PROJECT / 'inbox'

parse_html = partial(fromstring, parser=HTMLParser(encoding='utf8'))
parse_xml = fromstring


def load_json(path: Path):
    with path.open('r', encoding='utf8') as f:
        return loads(f.read())


def clean_up_last_check_results():
    subs_urls = {sub.url for sub in SUBS}
    unsubscribed_urls = LAST_CHECK_RESULTS.keys() - subs_urls
    if not unsubscribed_urls:
        return
    logger.info(
        'deleting %d unsubscribed urls from %s: %s',
        len(unsubscribed_urls),
        LAST_CHECK_RESULTS_PATH,
        unsubscribed_urls,
    )
    for unsubscribed in unsubscribed_urls:
        del LAST_CHECK_RESULTS[unsubscribed]


LAST_CHECK_RESULTS_PATH = PROJECT / 'last_check_results.json'
LAST_CHECK_RESULTS = load_json(LAST_CHECK_RESULTS_PATH)


clean_up_last_check_results()


def save_json(path: Path, data: dict):
    with path.open('w', encoding='utf8') as f:
        f.write(
            dumps(
                data,
                ensure_ascii=False,
                check_circular=False,
                sort_keys=True,
                indent='\t',
            )
        )


session_manager = SessionManager(timeout=ClientTimeout(30))


async def read(url, ssl):
    try:
        response = await session_manager.get(url, ssl=ssl)
        return await response.read()
    except Exception as e:
        logger.error(f'{e!r} on {url}')
        return


def get_checked_links(url):
    try:
        return set(LAST_CHECK_RESULTS[url])
    except KeyError:
        return ()


def parse(doctype, body):
    if doctype == 'xml':
        return parse_xml(body)
    return parse_html(body)


async def check(sub: Subscription):
    main_url: str = sub.url

    body = await read(main_url, sub.ssl)
    if body is None:
        # logger.error('text is None for %s', main_url)
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

    last_checked = LAST_CHECK_RESULTS.setdefault(main_url, {})

    # convert relative links to absolute
    urls = {urljoin(main_url, link): False for link in links}

    # delete old urls that no longer exist
    for k in last_checked.keys() - urls.keys():
        del last_checked[k]

    items = []
    for url, title in zip(urls, titles):
        if last_checked.setdefault(url, False):
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
