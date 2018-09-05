# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import functools
import logging
import sys

from apscheduler.schedulers.blocking import BlockingScheduler
import click
import datadog

from monitor import config, reporting
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

    mirror = config.mirror_config_from_environ()

    if node_ids:
        for node_id in node_ids:
            status = determine_commit_replication_status(mirror, node_id)
            reporting.print_replication_lag(mirror, status)
    else:
        pulse_config = config.pulse_config_from_environ()
        run_pulse_listener(
            pulse_config.PULSE_USERNAME,
            pulse_config.PULSE_PASSWORD,
            pulse_config.PULSE_EXCHANGE,
            pulse_config.PULSE_QUEUE_NAME,
            pulse_config.PULSE_QUEUE_ROUTING_KEY,
            pulse_config.PULSE_QUEUE_READ_TIMEOUT,
            True,
            worker_args=dict(
                mirror_config=mirror, reporting_function=reporting.print_replication_lag
            ),
        )


@click.command()
@click.option(
    "--debug",
    envvar="DEBUG",
    is_flag=True,
    help="Print debugging messages about the script's progress.",
)
@click.option(
    "--no-send",
    is_flag=True,
    help="Do not drain any queues or send any data. Useful for debugging.",
)
def report_lag(debug, no_send):
    """Measure and report repository replication lag to a metrics service."""

    if debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(stream=sys.stdout, level=log_level)

    mirror = config.mirror_config_from_environ()
    pulse_config = config.pulse_config_from_environ()

    if no_send:
        reporting_function = reporting.print_replication_lag
        empty_queue_function = None
    else:
        datadog.initialize()
        reporting_function = reporting.report_to_statsd
        empty_queue_function = functools.partial(
            reporting.report_all_caught_up_to_statsd, mirror
        )

    def job():
        run_pulse_listener(
            pulse_config.PULSE_USERNAME,
            pulse_config.PULSE_PASSWORD,
            pulse_config.PULSE_EXCHANGE,
            pulse_config.PULSE_QUEUE_NAME,
            pulse_config.PULSE_QUEUE_ROUTING_KEY,
            pulse_config.PULSE_QUEUE_READ_TIMEOUT,
            no_send,
            worker_args=dict(
                mirror_config=mirror, reporting_function=reporting_function
            ),
            empty_queue_callback=empty_queue_function,
        )

    sched = BlockingScheduler()

    # Run once right away, then run at intervals
    sched.add_job(job)
    sched.add_job(job, "interval", minutes=5)

    # This does not return
    sched.start()
