from __future__ import annotations

from ucits_etf_issuer_holdings.testing import RECORDED_ISINS, RecordedTransport, recorded_transport


def test_recorded_isins() -> None:
    assert RECORDED_ISINS == (
        "IE00B4L5Y983", "IE00B3F81409", "IE00BK5BQT80", "LU0274211480",
        "IE000BI8OT95", "LU1681043599", "IE00B5M1WJ87", "IE000716YHJ7",
    )  # fmt: skip


def test_unmatched_is_404() -> None:
    resp = recorded_transport().request("GET", "https://nowhere.example/")
    assert resp.status == 404
    assert resp.text == "not recorded"


def test_matches_by_method_url_and_params_as_strings() -> None:
    transport = recorded_transport()
    url = "https://dng-api.invesco.com/cache/v1/accounts/en_GB/shareclasses/IE000716YHJ7/holdings/fund"
    assert transport.request("GET", url, params={"idType": "isin"}).status == 200
    assert transport.request("GET", url, params={"idType": "sedol"}).status == 404
    assert transport.request("POST", url, params={"idType": "isin"}).status == 404


def test_match_json_is_a_recursive_subset() -> None:
    transport = recorded_transport()
    url = "https://www.amundietf.de/mapi/ProductAPI/getProductsData"
    body = {"context": {"countryCode": "DEU"}, "productIds": ["IE000BI8OT95"], "extra": 1}
    resp = transport.request("POST", url, json=body)
    assert resp.status == 200
    assert resp.json()["products"][0]["productId"] == "IE000BI8OT95"
    assert transport.request("POST", url, json={"productIds": ["IE000BI8OT95", "x"]}).status == 404
    assert transport.request("POST", url).status == 404


def test_binary_and_content_type() -> None:
    url = "https://etf.dws.com/etfdata/export/GBR/ENG/excel/product/constituent/LU0274211480/"
    resp = recorded_transport().request("GET", url)
    assert resp.content.startswith(b"PK")
    assert "spreadsheetml" in resp.content_type


def test_is_a_class_with_requests_counter() -> None:
    transport = RecordedTransport()
    transport.request("GET", "https://nowhere.example/")
    assert transport.requests == [("GET", "https://nowhere.example/")]
