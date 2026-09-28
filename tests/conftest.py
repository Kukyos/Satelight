def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="run tests that need the network")
