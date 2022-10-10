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


url_format = """\
[InternetShortcut]
URL={url}
""".format

config_path = project / 'config.json'
with config_path.open('r', encoding='utf8') as f:
    config = loads(f.read())


async def check(sub):
    main_url = sub['url'].rstrip('/')
    content = await (await client.get(main_url, ssl=sub.get('ssl'))).read()

    if sub['doctype'] == 'xml':
        xp = parse_xml(content).xpath
    else:
        xp = parse_html(content).xpath

    for xpath in sub['xpaths']:
        links_xp = xpath['links']
        titles_xp = xpath['titles']

        last_match = xpath.get('last_match')
        last_match = set(last_match) if last_match is not None else ()

        found_new_link = False

        links = xp(links_xp)

        # convert relative links to absolute
        urls = [main_url + link if link[0] == '/' else link for link in links]

        for url, title in zip(urls, xp(titles_xp)):
            if url in last_match:
                break

            title = title.strip().translate(slug_table)
            with open(inbox / f'{title}.URL', 'w', encoding='utf8') as f:
                f.write(url_format(url=url))

            if found_new_link is False:
                xpath['last_match'] = urls
                found_new_link = True
        else:
            if found_new_link is False:
                print(f'no match: {main_url=} {links_xp=}')


async def check_all():
    # noinspection PyGlobalUndefined
    global client
    async with ClientSession() as client:
        await gather(*[check(sub) for sub in config['subscriptions']])


run(check_all())


with config_path.open('w', encoding='utf8') as f:
    f.write(
        dumps(
            config,
            ensure_ascii=False,
            check_circular=False,
            sort_keys=True,
            indent='\t',
        )
    )

if inbox.files():
    import webbrowser

    webbrowser.open(inbox)
