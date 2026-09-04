import runner


def test_validate_url_blocks_localhost():
    ok, err = runner.validate_url("http://localhost:8080/api")
    assert not ok
    assert "blocked" in err.lower()


def test_validate_url_allows_public_host(monkeypatch):
    monkeypatch.delenv("ALLOWED_HOSTS", raising=False)

    class FakeInfo:
        def __init__(self, ip):
            self.ip = ip

        def __getitem__(self, idx):
            if idx == 4:
                return (self.ip,)
            raise IndexError

    monkeypatch.setattr(
        "runner.socket.getaddrinfo",
        lambda host, port: [FakeInfo("93.184.216.34")],
    )
    ok, err = runner.validate_url("https://example.com/path")
    assert ok
    assert err is None


def test_validate_url_allowed_hosts(monkeypatch):
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.com")
    ok, err = runner.validate_url("https://api.example.com/v1")
    assert ok

    ok, err = runner.validate_url("https://other.example.com/v1")
    assert not ok
    assert "ALLOWED_HOSTS" in err
