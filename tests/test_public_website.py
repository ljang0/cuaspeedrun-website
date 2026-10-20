"""Publication and upload checks using the real catalog and shipped scripts."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from export_public_catalog import RECORD_FIELDS  # noqa: E402


@pytest.fixture(scope="module")
def public_site(tmp_path_factory):
    output = tmp_path_factory.mktemp("public-site")
    subprocess.run([sys.executable, str(ROOT / "scripts/build_public_site.py"),
                    "--output", str(output)], cwd=ROOT, check=True)
    return output


def test_publication_preserves_catalog_and_links(public_site):
    catalog = json.loads((public_site / "results-catalog.json").read_text())
    home = BeautifulSoup((public_site / "index.html").read_text(), "html.parser")
    footer = home.select_one('.site-footer')
    assert 'cua-speedrun' in footer.get_text(' ', strip=True)
    assert 'sponsored by' not in footer.get_text(' ', strip=True)
    assert not footer.select('a[href="https://modal.com"]')
    for dataset in catalog['datasets'].values():
        page = BeautifulSoup((public_site / dataset['href']).read_text(), 'html.parser')
        assert json.loads(page.select_one('[data-results-data]').string) == dataset['records']
    # Known dynamic destinations go to the configured evaluator; all static
    # navigation/assets must be present in this offline publication.
    for filename in ['index.html', 'paper.html', 'docs.html', 'submit/index.html', '404.html']:
        page = BeautifulSoup((public_site / filename).read_text(), 'html.parser')
        for el in page.select('[href], [src]'):
            raw = el.get('href') or el.get('src')
            url = urlsplit(raw)
            if url.scheme or url.netloc or not url.path or url.path in ['/me', '/login/github']:
                continue
            path = public_site / url.path.lstrip('/')
            if url.path in ['/', '/submit']: path = path / 'index.html'
            assert path.is_file(), (filename, raw)
    assert not (public_site / 'paper.pdf').exists()


def test_public_results_only_include_paper_subsets(public_site):
    # The public repository and site carry only the exported display catalog,
    # never the private results sheet, its curation, or per-task evidence.
    assert not list((ROOT / 'data').rglob('*.csv'))
    assert not (ROOT / 'data/results-curation.json').exists()
    assert not (ROOT / 'data/results-evidence').exists()
    assert not list(public_site.rglob('*.csv'))
    assert not (public_site / 'results-evidence').exists()
    exported = json.loads((ROOT / 'data/public-catalog.json').read_text())
    catalog = json.loads((public_site / 'results-catalog.json').read_text())
    config = json.loads((ROOT / 'website/config.json').read_text())
    subsets = config['paper_subsets']
    assert list(exported['datasets']) == list(subsets)
    assert set(catalog['datasets']) == set(subsets)
    assert catalog['included_rows'] == exported['included_rows'] == sum(
        len(dataset['records']) for dataset in exported['datasets'].values())
    allowed = set(RECORD_FIELDS)
    for dataset in exported['datasets'].values():
        assert set(dataset) == {'name', 'label', 'href', 'task_counts', 'records'}
        for record in dataset['records']:
            assert set(record) <= allowed
    for filename in [ROOT / 'data/public-catalog.json', *public_site.rglob('*')]:
        if filename.suffix in {'.html', '.json', '.js', '.xml'}:
            text = filename.read_text()
            assert 'anonymousmypcbench/cua-speedrun-trajectories' not in text, filename
            assert '.csv' not in text, filename
    home = BeautifulSoup((public_site / 'index.html').read_text(), 'html.parser')
    overview = json.loads(home.select_one('[data-overview-data]').string)
    assert [d['name'] for d in overview] == list(subsets)
    providers = {p['prefix']: p['slug'] for p in config['providers']}
    for name, dataset in exported['datasets'].items():
        # The build only clears default-setting labels and marks ablations.
        for record in dataset['records']:
            if record['variant'] in config['default_variants']:
                record['variant'], record['series'] = '', record['model']
            record['ablation'] = record['variant'] in config['ablation_variants']
        assert catalog['datasets'][name]['records'] == dataset['records']
        interactive = next(d for d in overview if d['name'] == name)
        assert interactive['selected_tasks'] == dataset['task_counts'][0]
        for shown, source in zip(interactive['records'], dataset['records'], strict=True):
            shown = dict(shown)
            assert shown.pop('provider') == next(
                slug for prefix, slug in providers.items() if source['model'].startswith(prefix))
            assert shown == {key: source[key] for key in shown}
        page = BeautifulSoup((public_site / dataset['href']).read_text(), 'html.parser')
        assert len(page.select('.dataset-switcher .dataset-tab')) == 4


def test_homepage_race_replays_published_records(public_site):
    race = json.loads((ROOT / 'website/config.json').read_text())['race']
    catalog = json.loads((public_site / 'results-catalog.json').read_text())
    records = catalog['datasets'][race['subset']]['records']
    home = BeautifulSoup((public_site / 'index.html').read_text(), 'html.parser')
    lanes = home.select('[data-race] .race-lane')
    assert len(lanes) == len(race['runners'])
    for lane, want in zip(lanes, race['runners'], strict=True):
        record = next(r for r in records if all(
            (r[k] or '') == want[k] for k in ('model', 'effort', 'variant')))
        assert float(lane['data-time']) == record['time_per_task_sec']
        assert float(lane['data-score']) == record['performance']
        assert lane.select_one('.lane-name strong').get_text() == record['model']
        assert lane.select_one('.lane-name span').get_text() == record['effort']
    race_text = home.select_one('[data-race]').get_text(' ', strip=True)
    assert 'Claude Code' not in race_text and 'Direct API' not in race_text


def test_paper_figures_and_author_credit(public_site):
    figures = public_site / 'assets/figures'
    provenance = json.loads((figures / 'sources.json').read_text())
    expected_names = ['Pranjal Aggarwal', 'Lawrence Keunho Jang', 'Sean Welleck',
                      'Daniel Fried', 'Ruslan Salakhutdinov', 'Jing Yu Koh']
    page = BeautifulSoup((public_site / 'index.html').read_text(), 'html.parser')
    assert [a.get_text() for a in page.select('.authors a')] == expected_names
    assert [a.get_text() for a in page.select('.authors > span') if a.sup] == [
        'Pranjal Aggarwal*', 'Lawrence Keunho Jang*', 'Jing Yu Koh*']
    assert page.select_one('.author-contacts a')['href'] == (
        'mailto:pranjala@cs.cmu.edu,ljang@cs.cmu.edu,jingyuk@cs.cmu.edu')
    for record in provenance['figures']:
        for format in ['pdf', 'svg']:
            artifact = figures / record[format]
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == record[f'{format}_sha256']
        assert (figures / record['pdf']).read_bytes().startswith(b'%PDF-')
    assert page.select_one('#cite code')
    assert page.select_one('[data-cite-open]')['href'] == '#cite'


def test_run_page_opens_the_modal_notebook(public_site):
    page = BeautifulSoup((public_site / 'submit/index.html').read_text(), 'html.parser')
    config = json.loads((ROOT / 'website/config.json').read_text())
    assert page.select_one('.console-button')['href'] == config['notebook_url']
    assert not page.select('form')


def test_paper_destination_replaces_duplicate_article(public_site):
    config = json.loads((ROOT / 'website/config.json').read_text())
    paper_url = config['paper_url']
    page = BeautifulSoup((public_site / 'paper.html').read_text(), 'html.parser')
    assert page.select_one('meta[http-equiv="refresh"]')['content'] == '0;url=' + (paper_url or '/')
    assert page.select_one('link[rel="canonical"]')['href'] == (paper_url or config['site_url'])
    assert page.select_one('meta[name="robots"]')['content'] == 'noindex'
    assert not page.select('article, .abstract, .paper-figure')
    assert 'paper.html' not in (public_site / 'sitemap.xml').read_text()
    home = BeautifulSoup((public_site / 'index.html').read_text(), 'html.parser')
    assert ('Paper forthcoming' in home.get_text()) == (not paper_url)
    for filename in public_site.rglob('*.html'):
        rendered = BeautifulSoup(filename.read_text(), 'html.parser')
        assert not rendered.select('a[href^="/paper.html"]'), filename


def test_announced_paper_url_updates_links_and_redirect(tmp_path):
    # A real arXiv URL exercises the configurable destination in an isolated
    # build; the release configuration remains empty until our paper is public.
    paper_url = 'https://arxiv.org/abs/1706.03762'
    config = json.loads((ROOT / 'website/config.json').read_text())
    config['paper_url'] = paper_url
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps(config))
    output = tmp_path / 'public'
    output.mkdir()
    # A previously exported real PDF must not survive the new release policy.
    (output / 'paper.pdf').write_bytes((ROOT / 'website/assets/figures/overview.pdf').read_bytes())
    command = [sys.executable, str(ROOT / 'scripts/build_public_site.py'),
               '--config', str(config_path), '--output', str(output)]
    subprocess.run(command, cwd=ROOT, check=True)
    assert not (output / 'paper.pdf').exists()
    home = BeautifulSoup((output / 'index.html').read_text(), 'html.parser')
    assert home.select_one('.site-navigation a')['href'] == paper_url
    assert home.select_one('.release-links a[href="' + paper_url + '"]')
    assert paper_url in home.select_one('#cite code').get_text()
    assert 'Paper forthcoming' not in home.get_text()
    redirect = BeautifulSoup((output / 'paper.html').read_text(), 'html.parser')
    assert redirect.select_one('meta[http-equiv="refresh"]')['content'] == '0;url=' + paper_url
    for private_or_incomplete in ['https://arxiv.org/user/', 'https://arxiv.org/abs/']:
        config['paper_url'] = private_or_incomplete
        config_path.write_text(json.dumps(config))
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        assert result.returncode != 0
        assert 'announced arXiv abstract URL' in result.stderr


def test_goatcounter_tag_follows_the_site_code(public_site, tmp_path):
    config = json.loads((ROOT / 'website/config.json').read_text())
    page = BeautifulSoup((public_site / 'index.html').read_text(), 'html.parser')
    assert bool(page.select('script[data-goatcounter]')) == bool(config['goatcounter'])
    config['goatcounter'] = 'example'
    config_path = tmp_path / 'config.json'
    config_path.write_text(json.dumps(config))
    output = tmp_path / 'public'
    command = [sys.executable, str(ROOT / 'scripts/build_public_site.py'),
               '--config', str(config_path), '--output', str(output)]
    subprocess.run(command, cwd=ROOT, check=True)
    for filename in ['index.html', 'docs.html', 'results.html', 'submit/index.html', '404.html']:
        tag = BeautifulSoup((output / filename).read_text(), 'html.parser').select_one('script[data-goatcounter]')
        assert tag['data-goatcounter'] == 'https://example.goatcounter.com/count', filename
        assert tag['src'] == 'https://gc.zgo.at/count.js'
    config['goatcounter'] = 'https://example.goatcounter.com'
    config_path.write_text(json.dumps(config))
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    assert result.returncode != 0 and 'GoatCounter site code' in result.stderr
