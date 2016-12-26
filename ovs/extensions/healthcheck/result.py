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
Result processing module for the health check
"""
from ovs.extensions.healthcheck.helpers.helper import Helper


class _Colors(object):
    """
    Colors for Open vStorage healthcheck logging
    """

    DEBUG = '\033[94m'
    INFO = '\033[94m'
    SUCCESS = '\033[92m'
    WARNING = '\033[93m'
    FAILED = '\033[91m'
    EXCEPTION = '\033[91m'
    SKIPPED = '\033[95m'
    CUSTOM = '\033[94m'
    ENDC = '\033[0m'

    def __getitem__(self, item):
        return getattr(self, item)


class HCResults(object):
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
        'warning': 'WARNING',
        'custom': 'CUSTOM'
    }
    # Exclude info values in the dict
    EXCLUDED_MESSAGES = ['INFO']
    # Log types that need to be replaced before logging to file
    LOG_CHANGING = {
        "success": "info",
        "skip": "info",
        "custom": "info"
    }

    def __init__(self, print_progress=True):
        """
        Init method

        :param print_progress: print the progress yes or no
        :type print_progress: bool
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

    def _call(self, msg, test_name, error_message=None, custom_value=None):
        """
        Process a message with a certain short test_name and type error message

        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type msg: str
        :param error_message:
            * 'error'
            * 'success'
            * 'debug'
            * 'info'
            * 'skip'
            * 'exception'
            * 'warning'
        :type error_message: str
        :param custom_value: a custom value that will be added when the error_message = custom
        :param custom_value: object
        :return:
        """
        if Helper.enable_logging:
            error_type = self.MESSAGES[error_message]
            if not error_type or error_type not in self.SUPPORTED_TYPES:
                raise ValueError('Found no error_type')
            if test_name is not None:
                if error_type not in HCResults.EXCLUDED_MESSAGES:
                    # Enable custom error type:
                    if error_type == 'CUSTOM':
                        self.result_dict[test_name] = custom_value
                    else:
                        self.result_dict[test_name] = error_type
            self.counters[error_type] += 1

            if self.print_progress:
                print "{0}[{1}] {2}{3}".format(_Colors()[error_type], error_type, _Colors.ENDC, str(msg))

    def get_results(self, print_progress=False):
        """
        Prints the result for check_mk

        :param print_progress: print the progress yes or no
        :type print_progress: bool
        :return: results
        :rtype: dict
        """
        # Checked with Jeroen Maelbrancke for this
        excluded_messages = ['INFO', 'DEBUG']
        if print_progress:
            for key, value in sorted(self.result_dict.items(), key=lambda x: x[0]):
                if value not in excluded_messages:
                    print "{0} {1}".format(key, value)
        return self.result_dict

    def failure(self, msg, test_name=None):
        """
        Report a failure log

        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :return:
        """
        self._call(msg, test_name, 'error')

    def success(self, msg, test_name=None):
        """
        Report a success log

        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :return:
        """
        self._call(msg, test_name, 'success')

    def warning(self, msg, test_name=None):
        """
        Report a warning log

        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :return:
        """
        self._call(msg, test_name, 'warning')

    def info(self, msg, test_name=None):
        """
        Report a info log

        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :return:
        """
        self._call(msg, test_name, 'info')

    def exception(self, msg, test_name=None):
        """
        Report a exception log

        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :return:
        """
        self._call(msg, test_name, 'exception')

    def skip(self, msg, test_name=None):
        """
        Report a skipped log

        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :return:
        """
        self._call(msg, test_name, 'skip')

    def debug(self, msg, test_name=None):
        """
        Report a debug log

        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :return:
        """
        self._call(msg, test_name, 'debug')

    def custom(self, msg, test_name=None, value=None):
        """
        Report a custom log. The value will determine the tag

        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param value: Value added to the log
        :type value: object
        :return:
        """

        self._call(msg, test_name, 'custom', value)
