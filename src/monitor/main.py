# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""The core routines for this program."""
import logging
from typing import List, NamedTuple

from maya import MayaDT, MayaInterval, now

from monitor.config import Mirror
from monitor.hgmo import utc_hgwebdate
from monitor.util import requests_retry_session
from monitor import hgmo

log = logging.getLogger(__name__)


class ReplicationStatus(NamedTuple):
    """Represents a mirrored object's replication status: fresh or stale by X seconds.
    """

    is_stale: bool
    seconds_behind: int

    @classmethod
    def fresh(cls):
        """Return an instance representing no replication delay."""
        return cls(is_stale=False, seconds_behind=0)

    @classmethod
    def behind_by(cls, seconds_behind: int):
        """Return an instance representing a replication delay of X seconds."""
        return cls(is_stale=True, seconds_behind=seconds_behind)


def stale_since(datetime: MayaDT):
    """Return the time interval between now and a given point in the past."""
    return MayaInterval(start=datetime, end=now())


def is_stale(dt_interval: MayaInterval) -> bool:
    """Is the given time interval for a stale or fresh commit?"""
    return dt_interval.duration > 0


def commit_in_mirror(mirror, commit_sha: str) -> bool:
    """Is the given commit SHA present in the mirrored repository?"""
    # Example URL: https://phabricator.services.mozilla.com/rMOZILLACENTRAL7395257233f2fce9f80a7660cbfb2b91d379b28f
    url = f"{mirror.url}/r{mirror.repo_callsign}{commit_sha}"
    response = requests_retry_session().head(url)
    if response.status_code == 404:
        # The commit is missing from Phabricator.
        return False
    elif response.status_code == 200:
        # The commit has been imported into Phabricator.
        return True
    else:
        # Uh oh.
        # Check for other 4XX and 5XX errors.
        response.raise_for_status()
        # We should never get here.
        raise RuntimeError(
            f"Unknown http error talking to the Phabricator server! (HTTP status code {response.status_code}"
        )


def fetch_commit_publication_time(
    source_repository_url: str, commit_sha: str
) -> MayaDT:
    """Return a commit's publication time in the source repo."""
    changeset_json = hgmo.fetch_changeset(commit_sha, source_repository_url)
    utc_epoch = utc_hgwebdate(changeset_json["date"])
    return MayaDT(utc_epoch)


def determine_commit_replication_status(
    mirror: Mirror, commit_sha: str
) -> ReplicationStatus:
    """Return the replication status of a single changeset."""
    if not commit_in_mirror(mirror, commit_sha):
        delay = stale_since(
            fetch_commit_publication_time(mirror.source_repository_url, commit_sha)
        )
        return ReplicationStatus.behind_by(delay.timedelta.seconds)
    else:
        return ReplicationStatus.fresh()


def find_first_lagged_changset(
    mirror: Mirror, changesets: List[str]
) -> ReplicationStatus:
    """Return the replication delay of the first un-mirrored changeset in a commit list.

    If no commits are delayed it returns a lag of zero duration.
    """
    for commit_sha in changesets:
        status = determine_commit_replication_status(mirror, commit_sha)
        log.info(f"replication delay for changeset {commit_sha}: {status.seconds_behind} seconds")
        if status.is_stale:
            # Bail early, we don't need to check any other changesets.
            return status
    else:
        return ReplicationStatus.fresh()


def check_and_report_mirror_delay(changesets, mirror, reporting_function):
    """Check a mirrored repository's replication delay and report the result.

    Returns: ReplicationStatus for the mirror.
    """
    mirror_replication_status = find_first_lagged_changset(mirror, changesets)
    reporting_function(mirror, mirror_replication_status)
    return mirror_replication_status
