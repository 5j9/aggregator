from aiohttp.web import (
    Application,
    FileResponse,
    Request,
    Response,
    RouteTableDef,
    WebSocketResponse,
    run_app,
)

from collector import (
    LAST_CHECK_RESULTS,
    LAST_CHECK_RESULTS_PATH,
    check_all,
    logger,
    save_json,
)

rt = RouteTableDef()


@rt.get('/htmx')
async def htmx(_: Request) -> FileResponse:
    logger.debug('htmx')
    return FileResponse('htmx-1.9.4.js')


@rt.get('/htmx_ws')
async def htmx_ws(_: Request) -> FileResponse:
    logger.debug('htmx_ws')
    return FileResponse('htmx-ws-1.9.4.js')


@rt.get('/items')
async def items(request: Request) -> WebSocketResponse:
    logger.debug('items')

    ws = WebSocketResponse()
    await ws.prepare(request)

    async for items in check_all():
        items_html = '\n'.join(items)
        s = f'<div id="items" hx-swap-oob="beforeend">{items_html}</div>'
        await ws.send_str(s)

    await ws.send_str(
        '<div id="items" hx-swap-oob="afterend">'
        '<div>All items checked.</div>'
        '<button hx-get="/mark_all_as_read" hx-swap="delete" hx-target="#items">Mark all as read</button>'
        '<div>'
    )

    return ws


@rt.get('/')
async def inbox(_: Request) -> FileResponse:
    logger.debug('inbox')
    return FileResponse('inbox.html')


@rt.get('/mark_as_read')
async def mark_as_read(request) -> Response:
    q = request.query
    logger.debug('marking %s as read', q['url'])
    LAST_CHECK_RESULTS[q['main_url']][q['url']] = True
    save_json(LAST_CHECK_RESULTS_PATH, LAST_CHECK_RESULTS)
    return Response(text='', content_type='text/html')


@rt.get('/mark_all_as_read')
async def mark_all_as_read(_: Request) -> Response:
    logger.info('marking all as read')
    for main_url, d in LAST_CHECK_RESULTS.items():
        for url, is_read in d.items():
            if is_read is False:
                logger.debug('marking %s as read', url)
                d[url] = True
    save_json(LAST_CHECK_RESULTS_PATH, LAST_CHECK_RESULTS)
    return Response(text='', content_type='text/html')


app = Application()
app.add_routes(rt)


def run():
    import webbrowser

    webbrowser.open(f'http://localhost:{port}/')
    run_app(app, host=host, port=port)


host = '127.0.0.1'
port = 8080


if __name__ == '__main__':
    run()
