# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import eventlet
eventlet.monkey_patch()
import fcntl
import os
import sys
import signal
import resource
import logging
import atexit
from logging import handlers


RunningGreenDaemons = set()


class StreamToLogger(object):
    """
    Fake file-like stream object that redirects writes to a logger instance.
    """
    def __init__(self, logger, log_level=logging.INFO):
        self.logger = logger
        self.log_level = log_level
        self.linebuf = ''

    def write(self, buf):
        for line in buf.rstrip().splitlines():
            self.logger.log(self.log_level, line.rstrip())


def sigterm_handler(signum, frame):
    """
    Call actions will be done after SIGTERM.
    """
    for daemon in RunningGreenDaemons:
        daemon.sigterm()
    sys.exit(0)


def sighup_handler(signum, frame):
    """
    Call actions will be done after SIGHUP.
    """
    for daemon in RunningGreenDaemons:
        daemon.sighup()


class Daemonize(object):
    """ Daemonize object
    Object constructor expects three arguments:
    - app: contains the application name which will be sent to logger.
    - pid: path to the pidfile.
    """

    def __init__(self, app, pid):
        self.app = app
        self.pid = pid
        self.debug = getattr(self, 'debug', False)
        # Initialize logging.
        self.logger = logging.getLogger(self.app)
        if self.debug:
            self.loglevel = logging.DEBUG
        elif hasattr(self, 'loglevel'):
            pass
        else:
            self.loglevel = logging.ERROR
        self.logger.setLevel(self.loglevel)
        # Display log messages only on defined handlers.
        self.logger.propagate = False
        # It will work on OS X and Linux. No FreeBSD support, guys, I don't want to import re here
        # to parse your peculiar platform string.
        if sys.platform == "darwin":
            syslog_address = "/var/run/syslog"
        else:
            syslog_address = "/dev/log"
        syslog = handlers.SysLogHandler(syslog_address)
        syslog.setLevel(self.loglevel)
        # Try to mimic to normal syslog messages.
        formatter = logging.Formatter("%(asctime)s %(name)s: %(message)s",
                                      "%b %e %H:%M:%S")
        syslog.setFormatter(formatter)
        self.logger.addHandler(syslog)

    def run(self):
        """
        Method representing the thread’s activity.
        You may override this method in a subclass.
        """
        import time
        time.sleep(25)
        self.logger.warn("green-daemon body. You must redefine run() method ")

    def sighup(self):
        """
        Method, that will be call while SIGHUP received
        """
        self.logger.warn("Caught signal HUP. Reloading.")

    def sigterm(self):
        """
        Method, that will be call while SIGTERM received
        """
        self.logger.warn("Caught signal TERM. Stopping daemon.")
        os.remove(self.pid)

    def start(self):
        """ start method
        Main daemonization process.
        """
        RunningGreenDaemons.add(self)

        try:
            if os.fork() > 0:
                sys.exit(0)     # kill off parent
        except OSError as e:
            self.logger.error("fork #1 failed: {errno} {errmsg}".format(errno=e.errno, errmsg=e.strerror))
            sys.exit(1)
        self.logger.debug("fork #1 succeful.")
        os.setsid()
        os.chdir('/')
        os.umask(0o022)

        # Second fork
        try:
            if os.fork() > 0:
                sys.exit(0)
        except OSError as e:
            self.logger.error("fork #2 failed: {errno} {errmsg}".format(errno=e.errno, errmsg=e.strerror))
            sys.exit(1)
        self.logger.debug("fork #2 succeful.")

        devnull = os.devnull if hasattr(os, "devnull") else "/dev/null"
        si = os.open(devnull, os.O_RDWR)
        os.dup2(si, sys.stdin.fileno())

        sys.stdout = StreamToLogger(self.logger, logging.INFO)
        sys.stderr = StreamToLogger(self.logger, logging.ERROR)

        # Create a lockfile so that only one instance of this daemon is running at any time.
        lockfile = open(self.pid, "w")
        # Try to get an exclusive lock on the file. This will fail if another process has the file
        # locked.
        fcntl.lockf(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)

        # Record the process id to the lockfile. This is standard practice for daemons.
        pid = os.getpid()
        lockfile.write("{pid}".format(pid=pid))
        lockfile.flush()

        # Set custom action on SIGTERM.
        signal.signal(signal.SIGTERM, sigterm_handler)
        signal.signal(signal.SIGHUP, sighup_handler)

        self.logger.info("Daemonized succefuly, PID={pid}".format(pid=pid))

        self.run()