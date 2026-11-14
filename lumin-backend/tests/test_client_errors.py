"""Cleaning rules for browser error reports (pure: no database, no web server)."""
from app.client_errors import MAX_MESSAGE, clean_path, one_line, scrub


def test_tokens_and_addresses_are_removed():
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijk"
    out = scrub(f"failed with {jwt} for me@example.com", 500)
    assert "eyJ" not in out and "me@example.com" not in out
    assert "[token]" in out and "[email]" in out


def test_bearer_and_secret_params_are_removed():
    out = scrub("Authorization: Bearer abc123def456ghi789 GET /x?token=SECRET123&page=2", 500)
    assert "abc123def456" not in out and "SECRET123" not in out
    assert "page=2" in out  # only the secret-looking parameter goes


def test_length_is_capped():
    assert len(scrub("x" * 9000, MAX_MESSAGE)) == MAX_MESSAGE
    assert scrub(None, 10) == "" and scrub("", 10) == ""


def test_path_keeps_only_the_path():
    assert clean_path("/v/123?token=x#frag") == "/v/123"
    assert clean_path("https://evil.example/x") == ""  # not a path
    assert clean_path(None) == ""
    assert len(clean_path("/" + "a" * 900)) <= 200


def test_line_breaks_cannot_fake_a_log_line():
    assert "\n" not in one_line("a\nINFO fake line\r\nb")
