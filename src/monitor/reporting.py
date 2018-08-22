# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""Functions for reporting this program's results"""
import click

from monitor.main import ReplicationStatus


def print_replication_lag(_, replication_status: ReplicationStatus):
    if replication_status.is_stale:
        report = click.style(
            str(replication_status.seconds_behind), fg="yellow", bold=True
        )
    else:
        report = click.style("0", fg="green", bold=True)

    click.echo("replication lag (seconds): ", nl=False)
    click.echo(report)
