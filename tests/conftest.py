from datetime import datetime, timedelta, timezone

import pytest

from merchant_notebook.commands import Session


class Clock:
    def __init__(self):
        self.t = datetime(2026, 11, 17, 14, 30, 0, tzinfo=timezone.utc)

    def __call__(self):
        self.t += timedelta(seconds=60)
        return self.t


@pytest.fixture
def data_dir(tmp_path):
    return tmp_path / "merchant_data"


@pytest.fixture
def make_session(data_dir):
    def make(confirm=lambda question: False, directory=None):
        return Session(directory or data_dir, confirm=confirm, now=Clock())
    return make


@pytest.fixture
def session(make_session):
    return make_session()


def active(session):
    return session.records[session.active]
