from json import loads, dumps
from functools import partial
from asyncio import run, gather

from aiohttp import ClientSession
from lxml import etree
from path import Path


slug_table = str.maketrans(r'\/:*?"<>|', '-' * 9)

project = Path(__file__).parent
inbox = project / 'inbox'

parse_html = partial(etree.fromstring, parser=etree.HTMLParser())
parse_xml = etree.fromstring


def load(path: Path):
    with path.open('r', encoding='utf8') as f:
        return loads(f.read())


url_format = """\
[InternetShortcut]
URL={link}
""".format

config = load(project / 'config.json')

last_links_path = project / 'last_links.json'
last_links = load(last_links_path)


async def check(sub):
    url = sub['url']
    content = await (await client.get(url, ssl=sub.get('ssl'))).read()

    if sub['doctype'] == 'xml':
        xp = parse_xml(content).xpath
    else:
        xp = parse_html(content).xpath

    url_last_links = last_links.setdefault(url, {})

    for links_xp, titles_xp in sub['link_title_xpaths']:
        last_link = url_last_links.get(links_xp)
        last_list_was_updated = False

        for link, title in zip(xp(links_xp), xp(titles_xp)):
            if link == last_link:
                break
            if link[0] == '/':  # relative link
                link = url.rstrip('/') + link
            title = title.strip().translate(slug_table)
            with open(inbox / f'{title}.URL', 'w', encoding='utf8') as f:
                f.write(url_format(link=link))

            if last_list_was_updated is False:
                url_last_links[links_xp] = link
                last_list_was_updated = True
        else:
            if last_list_was_updated is False:
                print(f'no match: {url=} {links_xp=}')


async def check_all():
    # noinspection PyGlobalUndefined
    global client
    async with ClientSession() as client:
        await gather(*[check(sub) for sub in config['subscriptions']])


run(check_all())


with last_links_path.open('w', encoding='utf8') as f:
    f.write(
        dumps(
            last_links,
            ensure_ascii=False,
            check_circular=False,
            sort_keys=True,
            indent='\t',
        )
    )

if inbox.files():
    import webbrowser

    webbrowser.open(inbox)
