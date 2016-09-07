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

from ovs.extensions.healthcheck.utils.extension import Utils
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
    MODULE = "utils"
    MESSAGES = {
        'failure': 'FAILED',
        'success': 'SUCCESS',
        'debug': 'DEBUG',
        'info': 'INFO',
        'skip': 'SKIPPED',
        'exception': 'EXCEPTION',
        'warning': 'WARNING'
    }

    def __init__(self, unattended_mode, silent_mode=False):
        """
        Init method for the HealthCheck Log handler

        :param unattended_mode: determines the attended modus you are running
            * unattended run (for monitoring)
            * attended run (for user)
        :param silent_mode: determines if you are running in silent mode
            * silent run (to use in-code)

        :type unattended_mode: bool
        :type silent_mode: bool
        """
        # Utils log settings (determine modus)
        if silent_mode:
            # if silent_mode is true, the unattended is also true
            self.unattended_mode = True
            self.silent_mode = True
        else:
            self.unattended_mode = unattended_mode
            self.silent_mode = False

        # Setup supported types
        self.SUPPORTED_TYPES = list(self.MESSAGES.values())

        # Setup HC counters
        self.counters = {}
        for stype in self.SUPPORTED_TYPES:
            self.counters[stype] = 0

        # Result of healthcheck in dict form
        self.healthcheck_dict = {}

        self._logger = LogHandler.get("healthcheck")

    def _log(self, msg, unattended_mode_name, unattended_print_mode=True, error_type=None):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """

        if not error_type or error_type not in self.SUPPORTED_TYPES:
            raise ValueError('Found no error_type')
        if Utils.enable_logging:
            self._logger.error('{0} - {1}'.format(error_type, msg))

        self.counters[error_type] += 1

        if not self.silent_mode:
            if self.unattended_mode:
                if unattended_print_mode:
                    print "{0} {1}".format(unattended_mode_name, error_type)
                    self.healthcheck_dict[unattended_mode_name] = error_type
            else:
                print "{0}[{1}] {2}{3}".format(_Colors()[error_type], error_type, _Colors.ENDC, str(msg))
        else:
            if unattended_print_mode:
                self.healthcheck_dict[unattended_mode_name] = error_type

    def failure(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._log(msg, unattended_mode_name, unattended_print_mode, self.MESSAGES['failure'])

    def success(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._log(msg, unattended_mode_name, unattended_print_mode, self.MESSAGES['success'])

    def warning(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._log(msg, unattended_mode_name, unattended_print_mode, self.MESSAGES['warning'])

    def info(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._log(msg, unattended_mode_name, unattended_print_mode, self.MESSAGES['info'])

    def exception(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._log(msg, unattended_mode_name, unattended_print_mode, self.MESSAGES['exception'])

    def skip(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._log(msg, unattended_mode_name, unattended_print_mode, self.MESSAGES['skip'])

    def debug(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._log(msg, unattended_mode_name, unattended_print_mode, self.MESSAGES['debug'])
