import datetime
from json import loads
from pathlib import Path

from collector import con


def load_json(path: Path):
    with path.open('r', encoding='utf8') as f:
        return loads(f.read())


last_check_results_path = (
    Path(__file__).parent.parent / 'last_check_results.json'
)
last_check_results: dict = load_json(last_check_results_path)

now: str = str(datetime.datetime.now())
for source_url, item_urls in last_check_results.items():
    con.executemany(
        'INSERT INTO state VALUES(?, ?, ?)',
        [(source_url, item_url, now) for item_url in item_urls],
    )

con.commit()
con.close()
