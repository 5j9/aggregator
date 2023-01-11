from aiohttp import web

from collector import LAST_CHECK_RESULTS_PATH, logger, check_all, \
    LAST_CHECK_RESULTS, save_json


async def htmx(request):
    logger.debug('htmx')
    return web.FileResponse('htmx.min-1.8.4.js')


async def htmx_ws(request):
    logger.debug('htmx_ws')
    return web.FileResponse('htmx-ws-1.8.4.js')


async def items(request):
    logger.debug('items')

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for items in check_all():
        items_html = '\n'.join(items)
        s = f'<div id="items" hx-swap-oob="beforeend">{items_html}<div>'
        await ws.send_str(s)

    await ws.send_str(f'<div id="items" hx-swap-oob="beforeend">All items checked.<div>')
    async for msg in ws:
        ...  # todo

    return ws


async def inbox(request):
    logger.debug('inbox')
    return web.FileResponse('inbox.html')


async def mark_as_read(request):
    q = request.query
    logger.debug('marking %s as read', q['url'])
    LAST_CHECK_RESULTS[q['main_url']][q['url']] = True
    save_json(LAST_CHECK_RESULTS_PATH, LAST_CHECK_RESULTS)
    return web.Response(text='', content_type='text/html')


app = web.Application()
app.add_routes([
    web.get('/htmx', htmx),
    web.get('/htmx_ws', htmx_ws),
    web.get('/items', items),
    web.get('/', inbox),
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
