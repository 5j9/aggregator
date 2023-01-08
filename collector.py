import sys
from json import loads, dumps
from functools import partial
from asyncio import gather, TimeoutError
from urllib.parse import urljoin, quote_plus
from atexit import register

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientConnectorError
from lxml import etree
from path import Path


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
        title=title
    )


sys.excepthook = show_exception_and_confirm_exit


# SLUG = str.maketrans(r'\/:*?"<>|', '-' * 9)

PROJECT = Path(__file__).parent
INBOX = PROJECT / 'inbox'

parse_html = partial(etree.fromstring, parser=etree.HTMLParser())
parse_xml = etree.fromstring


def load_json(path: Path):
    with path.open('r', encoding='utf8') as f:
        return loads(f.read())


LAST_CHECK_RESULTS_PATH = PROJECT / 'last_check_results.json'
LAST_CHECK_RESULTS = load_json(LAST_CHECK_RESULTS_PATH)

CONFIG_PATH = PROJECT / 'config.json'
CONFIG = load_json(CONFIG_PATH)


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


register(save_json, LAST_CHECK_RESULTS_PATH, LAST_CHECK_RESULTS)


async def get_text(url, ssl):
    try:
        response = await CLIENT.get(url, ssl=ssl)
    except ClientConnectorError:
        logger.warning(f'ClientConnectorError on {url}.')
        return
    except TimeoutError:
        logger.warning(f'TimeoutError on {url}.')
        return

    return await response.text()


def get_checked_links(url):
    try:
        return set(LAST_CHECK_RESULTS[url])
    except KeyError:
        return ()


async def check(sub):
    main_url: str = sub['url']
    logger.debug('checking %s', main_url)

    text = await get_text(main_url, sub.get('ssl'))
    if text is None:
        logger.error('text is None for %s', main_url)
        return

    if sub['doctype'] == 'xml':
        xp = parse_xml(text).xpath
    else:
        xp = parse_html(text).xpath

    last_checked = LAST_CHECK_RESULTS.setdefault(main_url, {})

    xpath = sub['xpaths']
    links_xp = xpath['links']
    titles_xp = xpath['titles']

    links = xp(links_xp)

    if not links:
        logger.warning(f'no match: {main_url=} {links_xp=}')
        return

    # convert relative links to absolute
    urls = {urljoin(main_url, link): False for link in links}

    # delete old urls that no longer exist
    for k in (last_checked.keys() - urls.keys()):
        del last_checked[k]

    items = []
    for url, title in zip(urls, xp(titles_xp)):
        if last_checked.setdefault(url, False):
            break
        items.append(create_item(url, title.strip(), main_url))

    if items:
        logger.debug('found new items on %s', main_url)
    else:
        logger.debug('no new items on %s', main_url)
    return items


async def check_all():
    # noinspection PyGlobalUndefined
    global CLIENT
    async with ClientSession(timeout=ClientTimeout(10)) as CLIENT:
        results = await gather(*[check(sub) for sub in CONFIG['subscriptions']])
    return [items for r in results for items in r if r is not None]
