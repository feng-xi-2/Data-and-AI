import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))


def pytest_configure(config):
    config.addinivalue_line("markers", "cloud: hits the real Cosmos DB / GenAI platform / replica databases (run with -m cloud)")
