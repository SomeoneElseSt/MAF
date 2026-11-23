from maf.main import listen_port


def test_port_comes_from_the_base_url_when_it_has_one():
    assert listen_port("http://localhost:8000") == 8000
    assert listen_port("http://localhost:9100") == 9100


def test_production_base_url_without_a_port_uses_the_default():
    assert listen_port("https://maforum.net") == 8000
