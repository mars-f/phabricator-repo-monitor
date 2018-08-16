# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from typing import NamedTuple

import requests
from maya import now, MayaInterval, MayaDT


class Source(NamedTuple):
    repo_url: str


class Mirror(NamedTuple):
    url: str
    repo_callsign: str


def commit_in_mirror(mirror, commit_sha: str):
    # Example URL: https://phabricator.services.mozilla.com/rMOZILLACENTRAL7395257233f2fce9f80a7660cbfb2b91d379b28f
    url = f'{mirror.url}/r{mirror.repo_callsign}{commit_sha}'
    response = requests.head(url)
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
        raise RuntimeError(f"Unknown http error talking to the Phabricator server! (HTTP status code {response.status_code}")


def fetch_commit_publication_time(source: Source, commit_sha: str):
    # Example URL: https://hg.mozilla.org/mozilla-central/json-rev/deafa2891c61
    url = f'{source.repo_url}/json-rev/{commit_sha}'
    response = requests.get(url)
    response.raise_for_status()
    changeset_json = response.json()
    return MayaDT(changeset_json['date'][0])


def determine_mirror_replication_lag(source: Source, mirror: Mirror, commit_sha: str) -> MayaInterval:
    if not commit_in_mirror(mirror, commit_sha):
        return MayaInterval(start=fetch_commit_publication_time(source, commit_sha), end=now())
    else:
        return MayaInterval(start=now(), duration=0)



def report_replication_lag(interval: MayaInterval):
    print("replication lag (seconds):", interval.timedelta.seconds)


def main():
    import sys
    commit_sha = sys.argv[1]
    assert len(commit_sha) == 40
    source = Source(repo_url="https://hg.mozilla.org/integration/autoland/")
    mirror = Mirror(url="https://phabricator.services.mozilla.com", repo_callsign="MOZILLACENTRAL")
    lag = determine_mirror_replication_lag(source, mirror, commit_sha)
    report_replication_lag(lag)


if __name__ == "__main__":
    main()
