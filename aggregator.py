import sys
from json import loads, dumps
from functools import partial
from asyncio import run, gather, TimeoutError
from urllib.parse import urljoin

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientConnectorError
from lxml import etree
from path import Path


def show_exception_and_confirm_exit(exc_type, exc_value, tb):
    import traceback
    traceback.print_exception(exc_type, exc_value, tb)
    input("Press enter to exit.")
    raise SystemExit


def to_html(href_texts: list[tuple[str, str]]) -> str:
    return '<ol>' + '\n'.join([
        f'<li><a href="{href}">{text}</a></li>' for href, text in href_texts
    ]) + '</ol>'


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


def writefile(path: Path, content: str):
    try:
        with path.open('x', encoding='utf8') as f:
            f.write(content)
    except FileNotFoundError:
        path.parent.makedirs_p()
        writefile(path, content)


async def get_text(url, ssl):
    try:
        response = await CLIENT.get(url, ssl=ssl)
    except ClientConnectorError:
        input(f'ClientConnectorError on {url}.\nPress enter to continue.')
        return
    except TimeoutError:
        input(f'TimeoutError on {url}.\nPress enter to continue.')
        return

    return await response.text()


def get_checked_links(url):
    try:
        return set(LAST_CHECK_RESULTS[url])
    except KeyError:
        return ()


async def check(sub):
    main_url: str = sub['url']

    text = await get_text(main_url, sub.get('ssl'))
    if text is None:
        return

    if sub['doctype'] == 'xml':
        xp = parse_xml(text).xpath
    else:
        xp = parse_html(text).xpath

    for xpath in sub['xpaths']:
        links_xp = xpath['links']
        titles_xp = xpath['titles']

        links = xp(links_xp)
        if not links:
            print(f'no match: {main_url=} {links_xp=}')

        # convert relative links to absolute
        urls = [urljoin(main_url, link) for link in links]
        checked_links = get_checked_links(main_url)

        new_links: list[tuple[str, str]] = []

        for url, title in zip(urls, xp(titles_xp)):
            if url in checked_links:
                break
            new_links.append((url, title.strip()))

        if not new_links:
            return

        domain = main_url.partition('://')[2].partition('/')[0]
        writefile(
            INBOX / domain + '.html',
            to_html(new_links)
        )

        LAST_CHECK_RESULTS[main_url] = urls


async def check_all():
    # noinspection PyGlobalUndefined
    global CLIENT
    async with ClientSession(timeout=ClientTimeout(10)) as CLIENT:
        await gather(*[check(sub) for sub in CONFIG['subscriptions']])


def open_inbox():
    files = INBOX.files()
    if not files:
        return

    import webbrowser

    # more than one directory in INBOX
    webbrowser.open(INBOX)


run(check_all())


# save_json(CONFIG_PATH, CONFIG)
save_json(LAST_CHECK_RESULTS_PATH, LAST_CHECK_RESULTS)

open_inbox()
