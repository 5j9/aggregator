from json import loads, dumps

from httpx import Client
from regex import finditer
from path import Path

client = Client()

project = Path(__file__).parent
inbox = project / 'inbox'


def load(path: Path):
    with path.open('r', encoding='utf8') as f:
        return loads(f.read())


url_format = """\
[InternetShortcut]
URL={link}
""".format

sources = load(project / 'sources.json')

last_links_path = project / 'last_links.json'
last_links = load(last_links_path)

for source in sources:
    url = source['url']
    response = client.get(url)
    url_last_links = last_links.setdefault(url, {})

    for pattern in source['patterns']:
        last_link = url_last_links.get(pattern)
        last_list_was_updated = False

        for m in finditer(pattern, response.text):
            link = m['link']
            if link == last_link:
                break

            title = m['title'].strip()
            with open(inbox / f'{title}.URL', 'w', encoding='utf8') as f:
                f.write(url_format(link=link))

            if last_list_was_updated is False:
                url_last_links[pattern] = link
                last_list_was_updated = True
        else:
            if last_list_was_updated is False:
                print(f'no match: {url=} {pattern=}')


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
