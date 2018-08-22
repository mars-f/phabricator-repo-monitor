# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""Functions for reading application configuration values"""
import os
import types
from typing import NamedTuple


class Source(NamedTuple):
    """Configuration for a hg.mozilla.org source repository.

    Args:
        repo_url: The full URL of the source repository.
    """

    repo_url: str


class Mirror(NamedTuple):
    """Configuration for a repository mirror in Phabricator.

    Args:
        url: The base URL of the Phabricator installation.
        repo_callsign: The Phabricator callsign for the mirrored repository.
            e.g. 'MOZILLACENTRAL'
    """

    url: str
    repo_callsign: str


def repositories_from_environ():
    """Return a Source and Mirror repository configuration from os.environ."""
    source = Source(os.environ["SOURCE_REPOSITORY"])
    mirror = Mirror(
        os.environ.get("PHABRICATOR_URL", "https://phabricator.services.mozilla.com"),
        os.environ["REPOSITORY_CALLSIGN"],
    )
    return source, mirror


def pulse_config_from_environ():
    """Initialize a Pulse queue worker configuration from os.environ.

    See https://wiki.mozilla.org/Auto-tools/Projects/Pulse
    """
    return types.SimpleNamespace(
        PULSE_USERNAME=os.environ["PULSE_USERNAME"],
        PULSE_PASSWORD=os.environ["PULSE_PASSWORD"],
        PULSE_EXCHANGE=os.environ.get("PULSE_EXCHANGE", "exchange/hgpushes/v2"),
        PULSE_QUEUE_NAME=os.environ["PULSE_QUEUE_NAME"],
        PULSE_QUEUE_ROUTING_KEY=os.environ["PULSE_QUEUE_ROUTING_KEY"],
    )
