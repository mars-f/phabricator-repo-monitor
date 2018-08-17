# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from unittest.mock import patch

import maya

from monitor.main import determine_mirror_replication_lag


def replace_function(name, replacement):
    return patch(name, side_effect=replacement)


def true(*_):
    return True


def false(*_):
    return False


def empty(iter):
    return list(iter) == []


def test_lag_is_zero_if_commit_in_mirror():
    with replace_function('monitor.main.commit_in_mirror', true):
        assert determine_mirror_replication_lag(None, None, 0).duration == 0


def test_lag_is_commit_ts_if_commit_missing():
    def one_day_ago(*_):
        return maya.now().subtract(days=1)

    with replace_function('monitor.main.commit_in_mirror', false),\
            replace_function('monitor.main.fetch_commit_publication_time',  one_day_ago):
        lag = determine_mirror_replication_lag(None, None, 0)
        assert lag.timedelta.days == 1
