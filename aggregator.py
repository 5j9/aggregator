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


sys.excepthook = show_exception_and_confirm_exit


SLUG = str.maketrans(r'\/:*?"<>|', '-' * 9)

PROJECT = Path(__file__).parent
INBOX = PROJECT / 'inbox'

parse_html = partial(etree.fromstring, parser=etree.HTMLParser())
parse_xml = etree.fromstring


URL_FORMAT = """\
[InternetShortcut]
URL={url}
""".format


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
        with path.open('w', encoding='utf8') as f:
            f.write(content)
    except FileNotFoundError:
        path.parent.makedirs_p()
        writefile(path, content)


async def check(sub):
    main_url: str = sub['url']
    directory = INBOX / main_url.partition('://')[2].partition('/')[0].translate(SLUG)

    try:
        response = await CLIENT.get(main_url, ssl=sub.get('ssl'))
    except ClientConnectorError:
        input(f'ClientConnectorError on {main_url}.\nPress enter to continue.')
        return
    except TimeoutError:
        input(f'TimeoutError on {main_url}.\nPress enter to continue.')
        return

    content = await response.read()

    if sub['doctype'] == 'xml':
        xp = parse_xml(content).xpath
    else:
        xp = parse_html(content).xpath

    for xpath in sub['xpaths']:
        links_xp = xpath['links']
        titles_xp = xpath['titles']

        try:
            checked_links = LAST_CHECK_RESULTS[main_url]
        except KeyError:
            checked_links = ()
        else:
            checked_links = set(checked_links)

        found_new_link = False

        links = xp(links_xp)

        # convert relative links to absolute
        urls = [urljoin(main_url, link) for link in links]

        for url, title in zip(urls, xp(titles_xp)):
            if url in checked_links:
                break

            title = title.strip().translate(SLUG)
            writefile(directory / f'{title}.URL', URL_FORMAT(url=url))

            if found_new_link is False:
                LAST_CHECK_RESULTS[main_url] = urls
                found_new_link = True
        else:
            if found_new_link is False:
                print(f'no match: {main_url=} {links_xp=}')


async def check_all():
    # noinspection PyGlobalUndefined
    global CLIENT
    async with ClientSession(timeout=ClientTimeout(10)) as CLIENT:
        await gather(*[check(sub) for sub in CONFIG['subscriptions']])


def open_inbox():
    directories = INBOX.dirs()
    if not directories:
        return

    import webbrowser

    if len(directories) == 1:
        webbrowser.open(directories[0])
        return

    # more than one directory in INBOX
    webbrowser.open(INBOX)


run(check_all())


# save_json(CONFIG_PATH, CONFIG)
save_json(LAST_CHECK_RESULTS_PATH, LAST_CHECK_RESULTS)

open_inbox()
