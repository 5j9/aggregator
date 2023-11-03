from collector import Subscription


class Example(Subscription):
    url = 'http://example.com/'

    async def select(self):
        xpath = await self.xpath
        self.links = xpath('//a[@class="post-title"]/@href')
        self.titles = xpath('//a[@class="post-title"]/text()')


class AnyClassName(Subscription):
    url = 'https://example.com/path.aspx'
    ssl = False  # ignore ssl verification errors
    doctype = 'xml'  # default doctype is 'html', use 'xml' for parsing xml

    async def select(self) -> None:
        cssselect = await self.cssselect
        rows = cssselect('tr')[1:]
        self.links = links = []
        self.titles = titles = []
        for row in rows:
            try:
                href = row.cssselect('td:last-child a')[0].attrib['href']
            except IndexError:
                continue
            links.append(href)
            titles.append(row.cssselect('.subdesc')[0].text)
