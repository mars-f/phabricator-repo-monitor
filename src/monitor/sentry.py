# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
"""
Sentry client instance.
"""
from functools import wraps
from typing import Callable

from raven import Client

client = Client(
    # DSN is automatically pulled from os.environ if present
    # dsn='https://<key>:<secret>@sentry.io/<project>',
    include_paths=[__name__.split(".", 1)[0]],
    # The release name should come from the HEROKU_SLUG_COMMIT environment var.
    # release=fetch_git_sha(os.path.dirname(__file__)),
    processors=("raven.processors.SanitizePasswordsProcessor",),
)


def record_exceptions(f: Callable, ignored_exceptions=None):
    """Decorator that watches for exceptions and sends them to Sentry.

    This can be used for frameworks where you do not have access to the full exception
    while it is being raised, such as APScheduler.  Simply decorate the function that
    will be executed by the framework. The decorator will capture any exceptions it
    raises and send them to Sentry while still allowing the APScheduler code to handle
    them as it sees fit (which usually means turning them into out-of-stack job events).

    Args:
        f: The function to decorate.
        ignored_exceptions: A list of Exception types that Sentry should ignore.
    """

    if ignored_exceptions:
        ignored_exceptions = tuple(ignored_exceptions)

    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            if ignored_exceptions and isinstance(e, ignored_exceptions):
                # Ignore the exception, let the surrounding framework handle it.
                raise
            else:
                client.captureException()
                raise

    return wrapper
