"""Unit tests for the default-spec heuristic in actions.py.

These exercise the pure ``build_default_charts`` helper directly, so they need
no database, Solr, or running CKAN app.
"""
import ckanext.gwexplorer.actions as actions


def _field(fid, semantic, analytic, name=None):
    return {
        "fid": fid,
        "name": name or fid,
        "semanticType": semantic,
        "analyticType": analytic,
    }


def _names(charts):
    return [c["name"] for c in charts]


def _chans(chart, channel):
    return [f["fid"] for f in chart["encodings"].get(channel, [])]


def test_empty_fields_returns_no_charts():
    assert actions.build_default_charts([]) == []


def test_geographic_pair_builds_point_map():
    fields = [
        _field("latitude", "quantitative", "measure"),
        _field("longitude", "quantitative", "measure"),
        _field("pop", "quantitative", "measure"),
    ]
    charts = actions.build_default_charts(fields)
    assert charts, "expected at least a map chart"
    geo = charts[0]
    assert geo["config"]["coordSystem"] == "geographic"
    assert geo["config"]["geoms"] == ["poi"]
    assert _chans(geo, "latitude") == ["latitude"]
    assert _chans(geo, "longitude") == ["longitude"]


def test_geo_columns_excluded_from_statistical_chart():
    # lat/lon must not be scattered against each other once detected as coords.
    fields = [
        _field("lat", "quantitative", "measure"),
        _field("lon", "quantitative", "measure"),
        _field("city", "nominal", "dimension"),
        _field("pop", "quantitative", "measure"),
    ]
    charts = actions.build_default_charts(fields)
    assert _names(charts) == ["Map", "Summary"]
    summary = charts[1]
    assert summary["config"]["geoms"] == ["bar"]
    assert _chans(summary, "columns") == ["city"]
    assert _chans(summary, "rows") == ["pop"]


def test_temporal_plus_measure_builds_line():
    fields = [
        _field("date", "temporal", "dimension"),
        _field("sales", "quantitative", "measure"),
    ]
    charts = actions.build_default_charts(fields)
    assert _names(charts) == ["Trend"]
    assert charts[0]["config"]["geoms"] == ["line"]
    assert _chans(charts[0], "columns") == ["date"]
    assert _chans(charts[0], "rows") == ["sales"]


def test_dimension_plus_measure_builds_bar():
    fields = [
        _field("country", "nominal", "dimension"),
        _field("gdp", "quantitative", "measure"),
    ]
    charts = actions.build_default_charts(fields)
    assert _names(charts) == ["Summary"]
    assert charts[0]["config"]["geoms"] == ["bar"]


def test_two_measures_build_scatter():
    fields = [
        _field("height", "quantitative", "measure"),
        _field("weight", "quantitative", "measure"),
    ]
    charts = actions.build_default_charts(fields)
    assert _names(charts) == ["Scatter"]
    assert charts[0]["config"]["geoms"] == ["point"]
    assert charts[0]["config"]["defaultAggregated"] is False


def test_dimensions_only_falls_back_to_count_bar():
    fields = [_field("category", "nominal", "dimension")]
    charts = actions.build_default_charts(fields)
    assert _names(charts) == ["Count"]
    rows = charts[0]["encodings"]["rows"]
    assert rows[0]["aggName"] == "count"


def test_palette_contains_all_fields():
    fields = [
        _field("lat", "quantitative", "measure"),
        _field("lon", "quantitative", "measure"),
        _field("city", "nominal", "dimension"),
        _field("pop", "quantitative", "measure"),
    ]
    charts = actions.build_default_charts(fields)
    palette_measures = {f["fid"] for f in charts[0]["encodings"]["measures"]}
    palette_dims = {f["fid"] for f in charts[0]["encodings"]["dimensions"]}
    assert palette_measures == {"lat", "lon", "pop"}
    assert palette_dims == {"city"}
