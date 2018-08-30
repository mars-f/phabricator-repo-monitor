# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Functions for listening to the Mozilla Pulse service.

See https://wiki.mozilla.org/Auto-tools/Projects/Pulse
"""
import logging
import socket
import sys
from contextlib import closing
from functools import partial

# from datadog import statsd    # FIXME datadog
from kombu import Connection, Exchange, Queue

# from committelemetry.hgmo import changesets_for_pushid
# from committelemetry.telemetry import payload_for_changeset, send_ping
# from committelemetry.sentry import client as sentry   # FIXME sentry integration
from monitor.hgmo import changesets_for_pushid
from monitor.main import check_and_report_mirror_delay

log = logging.getLogger(__name__)


def noop(*args, **kwargs):
    return None


def process_push_message(body, message, no_send=False, extra_data=None):
    """Process a hg push message from Mozilla Pulse.

    The message body structure is described by https://mozilla-version-control-tools.readthedocs.io/en/latest/hgmo/notifications.html#common-properties-of-notifications

    Messages can be inspected by visiting https://tools.taskcluster.net/pulse-inspector?bindings[0][exchange]=exchange%2Fhgpushes%2Fv2&bindings[0][routingKeyPattern]=%23

    Args:
        body: The decoded JSON message body as a Python dict.
        message: A AMQP Message object.
        no_send: Do not send any ping data or drain any queues.
    """
    ack = noop if no_send else message.ack

    log.debug(f"received message: {message}")

    payload = body["payload"]
    log.debug(f"message payload: {payload}")

    msgtype = payload["type"]
    if msgtype != "changegroup.1":
        log.info(f"skipped message of type {msgtype}")
        ack()
        return

    pushlog_pushes = payload["data"]["pushlog_pushes"]
    # The count should always be 0 or 1.
    # See https://mozilla-version-control-tools.readthedocs.io/en/latest/hgmo/notifications.html#changegroup-1
    pcount = len(pushlog_pushes)
    if pcount == 0:
        log.info(f"skipped message with zero pushes")
        ack()
        return
    elif pcount > 1:
        # Raise this as a warning to draw attention.  According to
        # https://mozilla-version-control-tools.readthedocs.io/en/latest/hgmo/notifications.html#changegroup-1
        # this isn't supposed to happen, and we should contact the hgpush
        # service admin in #vcs on IRC.
        log.warning(
            f"skipped invalid message with multiple pushes (expected 0 or 1, got {pcount})"
        )
        ack()
        return

    pushdata = pushlog_pushes.pop()

    mirror = extra_data["mirror_config"]
    reporting_fn = extra_data["reporting_function"]

    changesets = changesets_for_pushid(pushdata["pushid"], pushdata["push_json_url"])
    replication_status = check_and_report_mirror_delay(changesets, mirror, reporting_fn)

    if replication_status.is_stale:
        # Don't ack() the message, leave processing where it is for the next job run.
        sys.exit(1)

    # The changesets in this push have all been replicated.  Move on to the next
    # push.
    ack()


def run_pulse_listener(
    username,
    password,
    exchange_name,
    queue_name,
    routing_key,
    timeout,
    no_send,
    worker_args=None,
    empty_queue_callback=None,
):
    """Run a Pulse message queue listener."""
    connection = build_connection(password, username)

    # Connect and pass in our own low value for retries so the connection
    # fails fast if there is a problem.
    connection.ensure_connection(
        max_retries=1
    )  # Retries must be >=1 or it will retry forever.

    with closing(connection):
        hgpush_exchange = Exchange(exchange_name, "topic", channel=connection)

        # Pulse queue names need to be prefixed with the username
        queue_name = f"queue/{username}/{queue_name}"
        queue = Queue(
            queue_name,
            exchange=hgpush_exchange,
            routing_key=routing_key,
            durable=True,
            exclusive=False,
            auto_delete=False,
            channel=connection,
        )

        # Passing passive=True will assert that the exchange exists but won't
        #  try to declare it.  The Pulse server forbids declaring exchanges.
        hgpush_exchange.declare(passive=True)

        # Queue.declare() also declares the exchange, which isn't allowed by
        # the Pulse server. Use the low-level Queue API to only declare the
        # queue itself.
        queue.queue_declare()
        queue.queue_bind()

        callback = partial(
            process_push_message, no_send=no_send, extra_data=worker_args
        )

        # Pass auto_declare=False so that Consumer does not try to declare the
        # exchange.  Declaring exchanges is not allowed by the Pulse server.
        with connection.Consumer(queue, callbacks=[callback], auto_declare=False):

            if no_send:
                log.info("transmission of monitoring data has been disabled")
                log.info("message acks has been disabled")

            log.info("reading messages")
            try:
                connection.drain_events(timeout=timeout)
            except socket.timeout:
                log.info("message queue is empty")
                if empty_queue_callback:
                    empty_queue_callback()

    log.info("done")


def build_connection(password, username):
    """Build a kombu.Connection object."""
    return Connection(
        hostname="pulse.mozilla.org",
        port=5671,
        ssl=True,
        userid=username,
        password=password,
    )
