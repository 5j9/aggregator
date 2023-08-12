from aiohttp import web

from collector import (
    LAST_CHECK_RESULTS,
    LAST_CHECK_RESULTS_PATH,
    check_all,
    logger,
    save_json,
)

rt = web.RouteTableDef()


@rt.get('/htmx')
async def htmx(request):
    logger.debug('htmx')
    return web.FileResponse('htmx-1.9.4.js')


@rt.get('/htmx_ws')
async def htmx_ws(request):
    logger.debug('htmx_ws')
    return web.FileResponse('htmx-ws-1.9.4.js')


@rt.get('/items')
async def items(request):
    logger.debug('items')

    ws = web.WebSocketResponse()
    await ws.prepare(request)

    async for items in check_all():
        items_html = '\n'.join(items)
        s = f'<div id="items" hx-swap-oob="beforeend">{items_html}<div>'
        await ws.send_str(s)

    await ws.send_str(
        f'<div id="items" hx-swap-oob="beforeend">All items checked.<div>'
    )
    async for msg in ws:
        ...  # todo

    return ws


@rt.get('/')
async def inbox(request):
    logger.debug('inbox')
    return web.FileResponse('inbox.html')


@rt.get('/mark_as_read')
async def mark_as_read(request):
    q = request.query
    logger.debug('marking %s as read', q['url'])
    LAST_CHECK_RESULTS[q['main_url']][q['url']] = True
    save_json(LAST_CHECK_RESULTS_PATH, LAST_CHECK_RESULTS)
    return web.Response(text='', content_type='text/html')


app = web.Application()
app.add_routes(rt)


def run():
    import webbrowser

    webbrowser.open(f'http://localhost:{port}/')
    web.run_app(app, host=host, port=port)


host = '127.0.0.1'
port = 8080


if __name__ == '__main__':
    run()
