import sys
from json import loads, dumps
from functools import partial
from asyncio import run, gather, TimeoutError

from aiohttp import ClientSession, ClientTimeout
from aiohttp.client_exceptions import ClientConnectorError
from lxml import etree
from path import Path


slug_table = str.maketrans(r'\/:*?"<>|', '-' * 9)

project = Path(__file__).parent
inbox = project / 'inbox'

parse_html = partial(etree.fromstring, parser=etree.HTMLParser())
parse_xml = etree.fromstring


url_format = """\
[InternetShortcut]
URL={url}
""".format


def load_json(path: Path):
    with path.open('r', encoding='utf8') as f:
        return loads(f.read())


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


CONFIG_PATH = project / 'config.json'
CONFIG = load_json(CONFIG_PATH)

LAST_CHECK_RESULTS_PATH = project / 'last_check_results.json'
LAST_CHECK_RESULTS = load_json(LAST_CHECK_RESULTS_PATH)


async def check(sub):
    main_url = sub['url'].rstrip('/') + '/'

    try:
        response = await client.get(main_url, ssl=sub.get('ssl'))
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
        urls = [main_url + link if link[0] == '/' else link for link in links]

        for url, title in zip(urls, xp(titles_xp)):
            if url in checked_links:
                break

            title = title.strip().translate(slug_table)
            with open(inbox / f'{title}.URL', 'w', encoding='utf8') as f:
                f.write(url_format(url=url))

            if found_new_link is False:
                LAST_CHECK_RESULTS[main_url] = urls
                found_new_link = True
        else:
            if found_new_link is False:
                print(f'no match: {main_url=} {links_xp=}')


async def check_all():
    # noinspection PyGlobalUndefined
    global client
    async with ClientSession(timeout=ClientTimeout(10)) as client:
        await gather(*[check(sub) for sub in CONFIG['subscriptions']])


run(check_all())


# save_json(CONFIG_PATH, CONFIG)
save_json(LAST_CHECK_RESULTS_PATH, LAST_CHECK_RESULTS)


if inbox.files():
    import webbrowser

    webbrowser.open(inbox)


def show_exception_and_confirm_exit(exc_type, exc_value, tb):
    import traceback
    traceback.print_exception(exc_type, exc_value, tb)
    input("Press enter to exit.")
    raise SystemExit


sys.excepthook = show_exception_and_confirm_exit
