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


@pytest.fixture(scope="module")
def public_site(tmp_path_factory):
    output = tmp_path_factory.mktemp("public-site")
    subprocess.run([sys.executable, str(ROOT / "scripts/build_public_site.py"),
                    "--output", str(output)], cwd=ROOT, check=True)
    return output


def test_publication_preserves_catalog_and_links(public_site):
    catalog = json.loads((public_site / "results-catalog.json").read_text())
    home = BeautifulSoup((public_site / "index.html").read_text(), "html.parser")
    assert 'powered by Modal' in home.get_text(' ', strip=True)
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
            if url.path == '/submit': path = path / 'index.html'
            assert path.is_file(), (filename, raw)
    assert not (public_site / 'paper.pdf').exists()


def test_public_results_only_include_paper_subsets(public_site, tmp_path):
    # Build the unchanged archive exporter first, then publish into the same
    # directory to check that old dataset URLs cannot leak into a later release.
    subprocess.run([sys.executable, str(ROOT / 'scripts/build_results_dashboard.py'),
                    '--output', str(tmp_path)], cwd=ROOT, check=True)
    archive = json.loads((tmp_path / 'results-catalog.json').read_text())
    subprocess.run([sys.executable, str(ROOT / 'scripts/build_public_site.py'),
                    '--output', str(tmp_path)], cwd=ROOT, check=True)
    catalog = json.loads((tmp_path / 'results-catalog.json').read_text())
    subsets = json.loads((ROOT / 'website/config.json').read_text())['paper_subsets']
    assert set(catalog['datasets']) == set(subsets)
    assert catalog['included_rows'] == 85
    assert catalog['publication_scope']['omitted_reviewed_rows'] == 11
    assert (tmp_path / 'trajectory-metrics.csv').read_bytes() == (
        ROOT / 'data/all-hf-model-trajectory-metrics-2026-09-13.csv').read_bytes()
    home = BeautifulSoup((tmp_path / 'index.html').read_text(), 'html.parser')
    overview = json.loads(home.select_one('[data-overview-data]').string)
    assert [d['name'] for d in overview] == list(subsets)
    for name, dataset in archive['datasets'].items():
        if name not in subsets:
            assert not (tmp_path / dataset['href']).exists()
            assert dataset['href'] not in (tmp_path / 'sitemap.xml').read_text()
            continue
        assert catalog['datasets'][name]['records'] == dataset['records']
        interactive = next(d for d in overview if d['name'] == name)
        assert interactive['selected_tasks'] == dataset['task_counts'][0]
        providers = {p['prefix']: p['slug'] for p in json.loads(
            (ROOT / 'website/config.json').read_text())['providers']}
        for shown, source in zip(interactive['records'], dataset['records'], strict=True):
            shown = dict(shown)
            assert shown.pop('provider') == next(
                slug for prefix, slug in providers.items() if source['model'].startswith(prefix))
            assert shown == {key: source[key] for key in shown}
        page = BeautifulSoup((tmp_path / dataset['href']).read_text(), 'html.parser')
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


def test_paper_figures_and_author_credit(public_site):
    figures = public_site / 'assets/figures'
    provenance = json.loads((figures / 'sources.json').read_text())
    expected_names = ['Pranjal Aggarwal', 'Lawrence Keunho Jang', 'Sean Welleck',
                      'Daniel Fried', 'Ruslan Salakhutdinov', 'Jing Yu Koh']
    for filename in ['index.html', 'paper.html']:
        page = BeautifulSoup((public_site / filename).read_text(), 'html.parser')
        assert [a.get_text() for a in page.select('.authors a')] == expected_names
        assert [a.get_text() for a in page.select('.authors > span') if a.sup] == [
            'Pranjal Aggarwal*', 'Lawrence Keunho Jang*', 'Jing Yu Koh*']
    for record in provenance['figures']:
        for format in ['pdf', 'svg']:
            artifact = figures / record[format]
            assert hashlib.sha256(artifact.read_bytes()).hexdigest() == record[f'{format}_sha256']
        assert (figures / record['pdf']).read_bytes().startswith(b'%PDF-')
    paper = BeautifulSoup((public_site / 'paper.html').read_text(), 'html.parser')
    assert {image['src'] for image in paper.select('.paper-figure img')} == {
        '/assets/figures/' + record['svg'] for record in provenance['figures']}


def test_submission_page_starts_disabled(public_site):
    page = BeautifulSoup((public_site / 'submit/index.html').read_text(), 'html.parser')
    assert all('disabled' in field.attrs for field in page.select('[data-auth-field]'))
    assert page.select_one('#modal-secret')['type'] == 'password'
    assert page.select_one('#agent-file')['name'] == 'agent_file'
    assert page.select_one('#billing-consent').has_attr('required')
