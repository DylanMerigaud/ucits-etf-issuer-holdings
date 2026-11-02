import pytest

from ucits_etf_holdings.errors import InvalidISIN
from ucits_etf_holdings.isin import normalize


def test_valid_isins_pass() -> None:
    for isin in ("IE00B4L5Y983", "IE00BK5BQT80", "LU0274211480", "US0378331005", "IE000716YHJ7"):
        assert normalize(isin) == isin


def test_strips_and_uppercases() -> None:
    assert normalize("  ie00b4l5y983\n") == "IE00B4L5Y983"


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "IE00B4L5Y98",
        "IE00B4L5Y9833",
        "1E00B4L5Y983",
        "IE00B4L5Y984",
        "IE00B4L5Y98X",
        "IE00B4L5-983",
    ],
)
def test_invalid_isins_raise(bad: str) -> None:
    with pytest.raises(InvalidISIN):
        normalize(bad)


def test_non_string_raises() -> None:
    with pytest.raises(InvalidISIN):
        normalize(None)  # type: ignore[arg-type]
