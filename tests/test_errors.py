from ucits_etf_issuer_holdings.errors import (
    FundNotFound,
    HoldingsError,
    InvalidISIN,
    IssuerUnavailable,
    NotListed,
    TransportError,
)


def test_all_subclass_holdings_error() -> None:
    for cls in (InvalidISIN, TransportError, NotListed, IssuerUnavailable, FundNotFound):
        assert issubclass(cls, HoldingsError)


def test_attributes() -> None:
    nl = NotListed("ishares", "IE00B4L5Y983", "not in index")
    assert (nl.issuer, nl.isin, nl.reason) == ("ishares", "IE00B4L5Y983", "not in index")
    iu = IssuerUnavailable("amundi", "HTTP 500")
    assert (iu.issuer, iu.reason) == ("amundi", "HTTP 500")
    fnf = FundNotFound("IE00B4L5Y983", {"ishares": "x", "vanguard": "y"})
    assert fnf.reasons == {"ishares": "x", "vanguard": "y"}
    assert "ishares: x" in str(fnf)
