# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

import logging
import sys

import click

import monitor.config
from monitor.main import determine_commit_replication_status
from monitor.pulse import run_pulse_listener


@click.command()
@click.option(
    "--debug",
    envvar="DEBUG",
    is_flag=True,
    help="Print debugging messages about the script's progress.",
)
@click.argument("node_ids", nargs=-1)
def display_lag(debug, node_ids):
    """Display the replication lag for a repo or an individual commit.

    Does not drain any queues or send any data.
    """
    if debug:
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)

    source, mirror = monitor.config.repositories_from_environ()

    if node_ids:
        for node_id in node_ids:
            status = determine_commit_replication_status(source, mirror, node_id)
            if status.is_stale:
                report = click.style(str(status.seconds_behind), fg="yellow", bold=True)
            else:
                report = click.style("0", fg="green", bold=True)
            click.echo("replication lag (seconds): ", nl=False)
            click.echo(report)
    else:
        pulse_config = monitor.config.pulse_config_from_environ()
        run_pulse_listener(
            pulse_config.PULSE_USERNAME,
            pulse_config.PULSE_PASSWORD,
            pulse_config.PULSE_EXCHANGE,
            pulse_config.PULSE_QUEUE_NAME,
            pulse_config.PULSE_QUEUE_ROUTING_KEY,
            0,
            True,
            worker_args=dict(source_repository_config=source, mirror_config=mirror),
        )
