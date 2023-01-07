from aiohttp import web, WSMsgType

from collector import logger, check_all, LAST_CHECK_RESULTS


async def htmx(request):
    with open('htmx.min-1.8.4.js') as f:
        text = f.read()
    return web.Response(text=text, content_type='text/javascript')


async def root(request):
    with open('inbox.html') as f:
        inbox = f.read()
    items = await check_all()
    if items:
        items_html = '\n'.join(items)
    else:
        items_html = 'Everything read!'

    inbox = inbox.replace('<div id="items">', '<div id="items">' + items_html)
    return web.Response(text=inbox, content_type='text/html')


async def mark_as_read(request):
    q = request.query
    logger.debug('marking %s as read', q['url'])
    LAST_CHECK_RESULTS[q['main_url']][q['url']] = True
    return web.Response(text='', content_type='text/html')


app = web.Application()
app.add_routes([
    web.get('/htmx', htmx),
    web.get('/', root),
    web.get('/mark_as_read', mark_as_read),
])


def run():
    import webbrowser
    webbrowser.open(f'http://localhost:{port}/')
    web.run_app(app, host=host, port=port)


host = '127.0.0.1'
port = 8080


if __name__ == '__main__':
    run()
