# Phabricator Repository Monitor

This program monitors source code repositories that have been mirrored in
Phabricator.

It measures and reports the replication delay between the mirrored
repository and its upstream repository.

---

## How it works

The program runs an internal scheduler that fires a check-and-report routine
every five minutes.

To check the repository replication delay the program reads mercurial repository push messages off of the Mozilla Pulse
`hgpush` message queue.  Each push contains multiple commits.  Pushes and the
commits inside them are in order, oldest to newest.

For each commit in a push the program checks for the existence of that push in
the Phabricator repository mirror.  If all commits in the push exist in Phabricator
then we assume the push has been fully mirrored to Phabricator. The
push message is removed from the queue, a lag of zero seconds is reported, and the
program moves on to the next push message.

If one or more commits in a push is missing from Phabricator then we assume the Phabricator
repository replication program is still working to catch up to the source repo.
Our program reports the replication delay as the difference between the current time and the time the push
to the source repo took place.  The delay-checking routine exits early and the push message is left at the head of the queue for the next run.


---

## Setup

You should use [pyenv](https://github.com/pyenv/pyenv) to make sure you are using
the same Python version listed in the Program's [Pipfile](Pipfile).

This project's dependencies are managed with [Pipenv](https://pipenv.readthedocs.io/en/latest/).  After you have
installed `pipenv` on your system run the following in the project root:

```console
$ pipenv install
```

You will need to create an account on [Mozilla
Pulse](https://wiki.mozilla.org/Auto-tools/Projects/Pulse) to collect messages about hgpush events.

This program is designed to run on Heroku and follows the [Heroku Architectural Principles](https://devcenter.heroku.com/articles/architecting-apps).
It reads its settings from environment variables.

See the file [dotenv.example.txt](dotenv.example.txt) in the project root for possible values.  These values must be present in your local and/or heroku execution
environments:

```console
$ cp dotenv.example.txt .env
$ vim .env
# Add your personal environment's configuration
```

Run the following command to check that everything works.  It won't send any data:

```console
$ env PYTHONPATH=src pipenv run bin/report-lag --no-send
```

---

## Development

### Environment setup

Install the development dependencies with `pipenv`:

```console
$ pipenv install --dev
```

### Hacking

Code formatting is done with [black](https://github.com/ambv/black).

Push event messages are read from a Pulse message queue. You can inspect a live hgpush 
message queue with [Pulse Inspector](https://tools.taskcluster.net/pulse-inspector?bindings[0][exchange]=exchange%2Fhgpushes%2Fv2&bindings[0][routingKeyPattern]=%23).

Messages use the [hgpush message format](https://mozilla-version-control-tools.readthedocs.io/en/latest/hgmo/notifications.html#changegroup-1).

Push events are generated from the [mercurial repo pushlogs](https://mozilla-version-control-tools.readthedocs.io/en/latest/hgmo/pushlog.html#writing-agents-that-consume-pushlog-data).

### Testing

#### Automated tests

The unit test suite can be run with [pytest](https://docs.pytest.org/en/latest/):

```console
$ pipenv run pytest
```

#### Manual/Smoke testing

You can smoke-test the program as follows:

```console
$ env PYTHONPATH=src pipenv run bin/report-lag --no-send --debug
```

---

## Usage

To get command-line help run the following:

```console
$ env PYTHONPATH=src pipenv run bin/report-lag --help
```

This script should be run on a Heroku standard dyno.

