from datetime import datetime

from aiohttp.web import (
    Application,
    FileResponse,
    Request,
    Response,
    RouteTableDef,
    WebSocketResponse,
    run_app,
)

from collector import check_all, con, cur, logger

rt = RouteTableDef()


@rt.get('/items')
async def items(request: Request) -> WebSocketResponse:
    logger.debug('items')

    ws = WebSocketResponse()
    await ws.prepare(request)

    async for items in check_all():
        items_html = '\n'.join(str(i) for i in items)
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
    return FileResponse('inbox.html')


@rt.get('/mark_as_read')
async def mark_as_read(request) -> Response:
    q = request.query
    logger.debug('marking %s as read', q['url'])
    cur.execute(
        'UPDATE state SET read_timestamp = ? WHERE item_url = ?',
        (str(datetime.now()), q['url']),
    )
    con.commit()
    return Response(text='', content_type='text/html')


@rt.get('/mark_all_as_read')
async def mark_all_as_read(_: Request) -> Response:
    logger.info('marking all as read')
    cur.execute(
        'UPDATE state SET read_timestamp = ? WHERE read_timestamp is Null',
        (str(datetime.now()),),
    )
    con.commit()
    return Response(text='', content_type='text/html')


app = Application()
app.add_routes(rt)


def run():
    import webbrowser

    port = 8080
    webbrowser.open(f'http://localhost:{port}/')
    run_app(app, host='127.0.0.1', port=port)


if __name__ == '__main__':
    run()
