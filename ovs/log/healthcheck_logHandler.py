#!/usr/bin/python

# Copyright (C) 2016 iNuron NV
#
# This file is part of Open vStorage Open Source Edition (OSE),
# as available from
#
#      http://www.openvstorage.org and
#      http://www.openvstorage.com.
#
# This file is free software; you can redistribute it and/or modify it
# under the terms of the GNU Affero General Public License v3 (GNU AGPLv3)
# as published by the Free Software Foundation, in version 3 as it comes
# in the LICENSE.txt file of the Open vStorage OSE distribution.
#
# Open vStorage is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY of any kind.

"""
LogHandler module for OVS health check
"""

from ovs.extensions.healthcheck.utils.helper import Helper
from ovs.log.log_handler import LogHandler


class _Colors(object):
    """
    Colors for Open vStorage healthcheck logging
    """

    DEBUG = '\033[94m'
    INFO = '\033[94m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    FAILED = '\033[91m'
    SKIPPED = '\033[95m'
    ENDC = '\033[0m'

    def __getitem__(self, item):
        return getattr(self, item)


class HCLogHandler(object):
    """
    Open vStorage Log Handler
    """
    # Statics
    MODULE = "helper"
    MESSAGES = {
        'error': 'FAILED',
        'success': 'SUCCESS',
        'debug': 'DEBUG',
        'info': 'INFO',
        'skip': 'SKIPPED',
        'exception': 'EXCEPTION',
        'warning': 'WARNING'
    }

    def __init__(self, print_progress=True):
        """
        Init method for the HealthCheck Log handler
        """
        self.print_progress = print_progress
        # Setup supported types
        self.SUPPORTED_TYPES = list(self.MESSAGES.values())

        # Setup HC counters
        self.counters = {}
        for stype in self.SUPPORTED_TYPES:
            self.counters[stype] = 0

        # Result of healthcheck in dict form
        self.result_dict = {}

        self._logger = LogHandler.get("healthcheck")

    def _log(self, msg, test_name, error_message=None):
        """
        :param msg: Log message for attended run
        :param test_name: name for monitoring output
        :return:
        """
        error_type = self.MESSAGES[error_message]
        if not error_type or error_type not in self.SUPPORTED_TYPES:
            raise ValueError('Found no error_type')
        if Helper.enable_logging:
            # skip/success uses info:
            if error_message == 'skip' or error_message == 'success':
                error_message = 'info'
            getattr(self._logger, error_message)('{0}'.format(msg))

        self.result_dict[test_name] = error_type
        self.counters[error_type] += 1

        if self.print_progress:
            print "{0}[{1}] {2}{3}".format(_Colors()[error_type], error_type, _Colors.ENDC, str(msg))

    def get_results(self, print_progress=False):
        """
        Prints the result for check_mk
        :return:
        """
        if print_progress:
            for key, value in sorted(self.result_dict.items(), key=lambda x: x[1]):
                if value in ['SUCCESS', 'FAILED']:
                    print "{0} {1}".format(key, value)
        return self.result_dict

    def failure(self, msg, test_name=None):
        """
        :param msg: Log message for attended run
        :param test_name: name for monitoring output
        :return:
        """
        self._log(msg, test_name, 'error')

    def success(self, msg, test_name=None):
        """
        :param msg: Log message for attended run
        :param test_name: name for monitoring output
        :return:
        """
        self._log(msg, test_name, 'success')

    def warning(self, msg, test_name=None):
        """
        :param msg: Log message for attended run
        :param test_name: name for monitoring output
        :return:
        """
        self._log(msg, test_name, 'warning')

    def info(self, msg, test_name=None):
        """
        :param msg: Log message for attended run
        :param test_name: name for monitoring output
        :return:
        """
        self._log(msg, test_name, 'info')

    def exception(self, msg, test_name=None):
        """
        :param msg: Log message for attended run
        :param test_name: name for monitoring output
        :return:
        """
        self._log(msg, test_name, 'exception')

    def skip(self, msg, test_name=None):
        """
        :param msg: Log message for attended run
        :param test_name: name for monitoring output
        :return:
        """
        self._log(msg, test_name, 'skip')

    def debug(self, msg, test_name=None):
        """
        :param msg: Log message for attended run
        :param test_name: name for monitoring output
        :return:
        """
        self._log(msg, test_name, 'debug')

    @staticmethod
    def test_finished():
        print ""
