# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import copy
from unittest.mock import patch

import kombu as kombu
import maya
import pytest

from monitor.cli import show_lag
from monitor.main import determine_commit_replication_lag
from click.testing import CliRunner


# This structure is described here:
# https://mozilla-version-control-tools.readthedocs.io/en/latest/hgmo/notifications.html#common-properties-of-notifications
# Example messages can be collected from this URL:
# https://tools.taskcluster.net/pulse-inspector?bindings[0][exchange]=exchange%2Fhgpushes%2Fv2&bindings[0][routingKeyPattern]=%23
test_message = {
    'payload': {
        'type': 'changegroup.1',
        'data': {
            'pushlog_pushes': [
                {
                    'time': 15278721560,
                    'pushid': 64752,
                    'push_json_url': 'https://hg.mozilla.org/integration/autoland/json-pushes?version=2&startID=64751&endID=64752',
                    'push_full_json_url': 'https://hg.mozilla.org/integration/autoland/json-pushes?version=2&full=1&startID=64751&endID=64752',
                    'user': 'someuser@mozilla.org',
                }
            ],
            'heads': ['ebe99842f5f8d543e5453ce78b1eae3641830b13'],
            'repo_url': 'https://hg.mozilla.org/integration/autoland',
        },
    }
}


@pytest.fixture
def memory_queue(monkeypatch):
    """Build an in-memory queue for acceptance tests."""
    connection = kombu.Connection(transport='memory')
    def build_connection(*_):
        return connection

    monkeypatch.setattr('monitor.pulse.build_connection', build_connection)

    # These values have been chosen so that they combine in just the right way
    # to produce a properly named Connection, Queue, and Exchange by the
    # run_pulse_listener() code.
    monkeypatch.setenv('PULSE_USERNAME', 'foo')
    monkeypatch.setenv('PULSE_PASSWORD', 'baz')
    monkeypatch.setenv('PULSE_EXCHANGE', 'queue/foo/bar')
    monkeypatch.setenv('PULSE_QUEUE_NAME', 'bar')
    monkeypatch.setenv('PULSE_QUEUE_ROUTING_KEY', 'integration/autoland')

    # This queue name has been constructed from the values above
    # to yield a valid Queue+Exchange combination.
    yield connection.SimpleQueue('queue/foo/bar')


def replace_function(name, replacement):
    return patch(name, side_effect=replacement)


def true(*_):
    return True


def false(*_):
    return False


def empty(iter):
    return list(iter) == []


def noop(*_, **__):
    pass


def trace(*args, **kwargs):
    print("echo", args, kwargs)


def test_lag_is_zero_if_commit_in_mirror():
    with replace_function("monitor.main.commit_in_mirror", true):
        assert determine_commit_replication_lag(None, None, 0).duration == 0


def test_lag_is_commit_ts_if_commit_missing():
    def one_day_ago(*_):
        return maya.now().subtract(days=1)

    with replace_function("monitor.main.commit_in_mirror", false), replace_function(
        "monitor.main.fetch_commit_publication_time", one_day_ago
    ):
        lag = determine_commit_replication_lag(None, None, 0)
        assert lag.timedelta.days == 1


def test_cli_show_lag_for_one_commit():
    def one_day_ago(*_):
        return maya.now().subtract(days=1)

    with replace_function("monitor.main.commit_in_mirror", false), replace_function(
        "monitor.main.fetch_commit_publication_time", one_day_ago
    ):
        runner = CliRunner()
        result = runner.invoke(show_lag, ["abcdef"])
        assert result.exit_code == 0
        assert "replication lag (seconds): 0" in result.output


def test_cli_show_lag_for_repo(memory_queue):

    def five_minutes_ago(*_):
        return maya.now().subtract(minutes=5)

    def changesets(*_):
        return ['aaa', 'bbb', 'ccc']

    memory_queue.put(copy.deepcopy(test_message))

    with replace_function("monitor.main.commit_in_mirror", false), replace_function(
        "monitor.main.fetch_commit_publication_time", five_minutes_ago
    ), replace_function("monitor.hgmo.changesets_for_pushid", changesets):
        runner = CliRunner()
        result = runner.invoke(show_lag)
        assert result.exit_code == 0
        assert "replication lag (seconds): 300" in result.output
