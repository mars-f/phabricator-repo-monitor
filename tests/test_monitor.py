# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import copy
from unittest.mock import ANY, patch

import kombu as kombu
import maya
import pytest
from click.testing import CliRunner

from monitor.cli import display_lag, report_lag
from monitor.main import (
    ReplicationStatus,
    determine_commit_replication_status,
    fetch_commit_publication_time,
    find_first_lagged_changset,
)
from monitor.config import Mirror
# This structure is described here:
# https://mozilla-version-control-tools.readthedocs.io/en/latest/hgmo/notifications.html#common-properties-of-notifications
# Example messages can be collected from this URL:
# https://tools.taskcluster.net/pulse-inspector?bindings[0][exchange]=exchange%2Fhgpushes%2Fv2&bindings[0][routingKeyPattern]=%23
from monitor.reporting import report_to_statsd

example_message = {
    "payload": {
        "type": "changegroup.1",
        "data": {
            "pushlog_pushes": [
                {
                    "time": 15278721560,
                    "pushid": 64752,
                    "push_json_url": "https://hg.mozilla.org/integration/autoland/json-pushes?version=2&startID=64751&endID=64752",
                    "push_full_json_url": "https://hg.mozilla.org/integration/autoland/json-pushes?version=2&full=1&startID=64751&endID=64752",
                    "user": "someuser@mozilla.org",
                }
            ],
            "heads": ["ebe99842f5f8d543e5453ce78b1eae3641830b13"],
            "source_repository_url": "https://hg.mozilla.org/integration/autoland",
        },
    }
}

# Example of a hg.mozilla.org commit taken from https://hg.mozilla.org/integration/autoland/json-rev/cc1ffa88e12c
example_commit = {
    "node": "cc1ffa88e12c75cf047757753589594c41d76ac5",
    "date": [1534452636.0, 0],
    "desc": 'Bug 1483600 - Notify "tab-content-frameloader-created" in GeckoView content script. r=jchen\n\nDifferential Revision: https://phabricator.services.mozilla.com/D3546',
    "backedoutby": "",
    "branch": "default",
    "bookmarks": [],
    "tags": [],
    "user": "Jane Smith \u003cjsmith@mozilla.com\u003e",
    "parents": ["07ce0e4ae08d0cd49d8be2c613121b5c84364422"],
    "phase": "public",
    "pushid": 67864,
    "pushdate": [1534452698, 0],
    "pushuser": "jsmith@mozilla.com",
    "landingsystem": "lando",
}

null_mirror = Mirror("", "", "")


@pytest.fixture(autouse=True)
def null_config(monkeypatch):
    monkeypatch.setenv("SOURCE_REPOSITORY", "")
    monkeypatch.setenv("REPOSITORY_CALLSIGN", "")


@pytest.fixture
def memory_queue(monkeypatch):
    """Build an in-memory queue for acceptance tests."""
    connection = kombu.Connection(transport="memory")

    def build_connection(*_):
        return connection

    monkeypatch.setattr("monitor.pulse.build_connection", build_connection)

    # These values have been chosen so that they combine in just the right way
    # to produce a properly named Connection, Queue, and Exchange by the
    # run_pulse_listener() code.
    monkeypatch.setenv("PULSE_USERNAME", "foo")
    monkeypatch.setenv("PULSE_PASSWORD", "baz")
    monkeypatch.setenv("PULSE_EXCHANGE", "queue/foo/bar")
    monkeypatch.setenv("PULSE_QUEUE_NAME", "bar")
    monkeypatch.setenv("PULSE_QUEUE_ROUTING_KEY", "integration/autoland")

    # This queue name has been constructed from the values above
    # to yield a valid Queue+Exchange combination.
    yield connection.SimpleQueue("queue/foo/bar")


def replace_function(name, replacement):
    return patch(name, side_effect=replacement)


def true(*_):
    return True


def false(*_):
    return False


def empty(iterable):
    return list(iterable) == []


def noop(*_, **__):
    pass


def trace(*args, **kwargs):
    print("echo", args, kwargs)


def test_lag_is_zero_if_commit_in_mirror():
    with replace_function("monitor.main.commit_in_mirror", true):
        status = determine_commit_replication_status(null_mirror, "aaaa")
        assert not status.is_stale
        assert status.seconds_behind == 0


def test_lag_is_commit_ts_if_commit_missing():
    def five_minutes_ago(*_):
        return maya.now().subtract(minutes=5)

    with replace_function("monitor.main.commit_in_mirror", false), replace_function(
        "monitor.main.fetch_commit_publication_time", five_minutes_ago
    ):
        status = determine_commit_replication_status(null_mirror, "aaaa")
        assert status.is_stale
        assert status.seconds_behind == 300


def test_most_lagged_changeset_zero_for_empty_list():
    status = find_first_lagged_changset(null_mirror, [])
    assert not status.is_stale
    assert status.seconds_behind == 0


def test_most_lagged_changeset_fresh_if_none_lagged():
    def return_fresh(*_):
        return ReplicationStatus.fresh()

    with replace_function(
        "monitor.main.determine_commit_replication_status", return_fresh
    ):
        status = find_first_lagged_changset(null_mirror, ["a", "b", "c"])
        assert not status.is_stale


def test_most_lagged_changeset_returns_first_lagged():
    fresh = ReplicationStatus.fresh()
    stale = ReplicationStatus.behind_by(10)
    lag_seq = iter([fresh, fresh, stale])

    def lag_fn(*_):
        return next(lag_seq)

    with replace_function("monitor.main.determine_commit_replication_status", lag_fn):
        status = find_first_lagged_changset(null_mirror, ["a", "b", "c"])
        assert status.is_stale
        assert status.seconds_behind == stale.seconds_behind


def test_cli_display_lag_for_one_commit():
    def delayed_five_minutes(*_):
        return ReplicationStatus.behind_by(300)

    with replace_function(
        "monitor.cli.determine_commit_replication_status", delayed_five_minutes
    ):
        runner = CliRunner()
        result = runner.invoke(display_lag, ["abcdef"])
        assert result.exit_code == 0
        assert "replication lag (seconds): 300" in result.output


def test_cli_display_lag_for_repo(memory_queue):
    def delayed_five_minutes(*_):
        return ReplicationStatus.behind_by(300)

    def changesets(*_):
        return ["aaa", "bbb", "ccc"]

    memory_queue.put(copy.deepcopy(example_message))

    with replace_function(
        "monitor.main.determine_commit_replication_status", delayed_five_minutes
    ), replace_function("monitor.hgmo.changesets_for_pushid", changesets):
        runner = CliRunner()
        result = runner.invoke(display_lag)
        assert result.exit_code == 1
        assert "replication lag (seconds): 300" in result.output


def test_cli_report_lag_for_repo(memory_queue):
    delay = ReplicationStatus.behind_by(300)

    def delayed_five_minutes(*_):
        return delay

    def changesets(*_):
        return ["aaa", "bbb", "ccc"]

    memory_queue.put(copy.deepcopy(example_message))

    with replace_function(
        "monitor.main.determine_commit_replication_status", delayed_five_minutes
    ), replace_function("monitor.hgmo.changesets_for_pushid", changesets), patch(
        "monitor.reporting.report_to_statsd"
    ) as report_to_statsd:
        runner = CliRunner()
        result = runner.invoke(report_lag)
        assert result.exit_code == 1
        report_to_statsd.assert_called_once_with(ANY, delay)


def test_cli_report_no_lag_for_repo_if_queue_empty(memory_queue):
    with patch("monitor.reporting.report_to_statsd") as report_to_statsd:
        runner = CliRunner()
        result = runner.invoke(report_lag)

        assert result.exit_code == 0
        report_to_statsd.assert_called_once_with(ANY, ReplicationStatus.fresh())


def test_fetch_commit_publication_time():
    commit = copy.deepcopy(example_commit)

    # See monitor.utc_hgwebdate() for the data format
    publication_time_as_epoch, publication_time_offset = 0, 0
    commit["date"] = [publication_time_as_epoch, publication_time_offset]

    with patch("monitor.hgmo.requests_retry_session") as session:
        session().get().json.return_value = commit
        publication_time = fetch_commit_publication_time(null_mirror, "aaa")
        assert publication_time.epoch == 0


def test_report_to_statsd():
    mirror = Mirror("", "", "TESTREPO")
    expected_stat_label = f"phabricator.repository.testrepo.seconds_behind_source_repo"

    status = ReplicationStatus.behind_by(5)
    expected_reported_delay = 5

    with patch("monitor.reporting.statsd") as statsd:
        report_to_statsd(mirror, status)
        statsd.gauge.assert_called_once_with(
            expected_stat_label, expected_reported_delay
        )
