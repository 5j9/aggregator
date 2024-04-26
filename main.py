from datetime import datetime
from pathlib import Path

from aiohttp.web import (
    Application,
    Request,
    Response,
    RouteTableDef,
    WebSocketResponse,
    run_app,
)
from aiohutils.server import static_path

from collector import check_all, con, cur, logger, recently_read_items

rt = RouteTableDef()


@rt.get('/new_items_ws')
async def new_items_ws(request: Request) -> WebSocketResponse:
    logger.debug('new_items_ws')

    ws = WebSocketResponse()
    await ws.prepare(request)

    async for items in check_all():
        items_html = '\n'.join(str(i) for i in items)
        s = f'<div id="items" hx-swap-oob="beforeend">{items_html}</div>'
        await ws.send_str(s)
    return ws


@rt.get('/new_items')
async def new_items(_: Request) -> Response:
    return Response(
        text='<div id="items" data-hx-ext="ws" data-ws-connect="/new_items_ws"></div>'
    )


@rt.get('/recent_reads')
async def recent_reads(_: Request) -> Response:
    items = recently_read_items(50)
    items_html = '\n'.join(str(i) for i in items)
    return Response(text='<div id="items">' + items_html + '</div>')


@rt.get('/')
async def index(_: Request) -> Response:
    with (aggregator_dir / 'index.html').open() as f:
        text = f.read()
    return Response(
        text=text.format(css_path=css_path), content_type='text/html'
    )


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


aggregator_dir = Path(__file__).parent
css_path, css_route = static_path(aggregator_dir / 'index.css')

app = Application()
app.add_routes([css_route, *rt])


def run():
    import webbrowser

    port = 8080
    webbrowser.open(f'http://localhost:{port}/')
    run_app(app, host='127.0.0.1', port=port)


if __name__ == '__main__':
    run()
