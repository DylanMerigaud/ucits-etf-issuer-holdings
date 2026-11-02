from ucits_etf_issuer_holdings.countries import name_of, to_iso2


def test_codes_pass_through() -> None:
    assert to_iso2("US") == "US"
    assert to_iso2("de") == "DE"


def test_names_resolve_case_insensitively() -> None:
    assert to_iso2("United States") == "US"
    assert to_iso2("  germany ") == "DE"
    assert to_iso2("Korea (South)") == "KR"


def test_unknown_and_empty() -> None:
    assert to_iso2("Atlantis") is None
    assert to_iso2("") is None
    assert to_iso2(None) is None
    assert to_iso2("ZZ") is None


def test_name_of() -> None:
    assert name_of("US") == "United States"
    assert name_of("fr") == "France"
    assert name_of("ZZ") is None
    assert name_of(None) is None
