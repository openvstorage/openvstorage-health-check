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


class HealthCheckResult(object):
    """
    Class to display the progress of the healthcheck
    Replaces the logger with a simpler version
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

    def __int__(self, print_progress=False):
        """

        :param unattended_mode: uses for unattended mode: a mode with output usable for check_mk
        :param silent_mode: outputs nothing on console, returns a dict with all results
        :return:
        """
        self.print_progress = print_progress

        # Setup supported types
        self.SUPPORTED_RESULTS = list(self.MESSAGES.values())

        # Setup HC counters
        self.counters = {}
        for result in self.SUPPORTED_RESULTS:
            self.counters[result] = 0

        # Result of healthcheck in dict form
        self.result_dict = {}

    def add_check_result(self, test, result, msg=None):
        """
        Adds a result to the dict
        :param test:
        :param result:
        :return:
        """
        if not result or result not in self.SUPPORTED_RESULTS:
            raise ValueError('Found no error_type')
        self.result_dict[test] = result
        self.counters[result] += 1

        if self.print_progress is True:
            self._display_entry(test, result)

    def _display_entry(self, test, result):
        """
        Prints the data
        :param test:
        :param result:
        :return:
        """
        pass

    def _print(self, msg, unattended_mode_name, unattended_print_mode=True, error_message=None):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        error_type = self.MESSAGES[error_message]
        if not error_type or error_type not in self.SUPPORTED_TYPES:
            raise ValueError('Found no error_type')
        if Utils.enable_logging:
            # skip/success uses info:
            if error_message == 'skip' or error_message == 'success':
                error_message = 'info'
            getattr(self._logger, error_message)('{0} - {1}'.format(error_type, msg))

        self.counters[error_type] += 1

        if not self.silent_mode:
            if self.unattended_mode:
                if unattended_print_mode:
                    print "{0} {1}".format(unattended_mode_name, error_type)
                    self.result_dict[unattended_mode_name] = error_type
            else:
                print "{0}[{1}] {2}{3}".format(_Colors()[error_type], error_type, _Colors.ENDC, str(msg))
        else:
            if unattended_print_mode:
                self.result_dict[unattended_mode_name] = error_type

    def failure(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._print(msg, unattended_mode_name, unattended_print_mode, 'failure')

    def success(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._print(msg, unattended_mode_name, unattended_print_mode, 'success')

    def warning(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._print(msg, unattended_mode_name, unattended_print_mode, 'warning')

    def info(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._print(msg, unattended_mode_name, unattended_print_mode, 'info')

    def exception(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._print(msg, unattended_mode_name, unattended_print_mode, 'exception')

    def skip(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._print(msg, unattended_mode_name, unattended_print_mode, 'skip')

    def debug(self, msg, unattended_mode_name, unattended_print_mode=True):
        """
        :param msg: Log message for attended run
        :param unattended_mode_name: name for monitoring output
        :param unattended_print_mode: describes if you want to print the output during a unattended run
        :return:
        """
        self._print(msg, unattended_mode_name, unattended_print_mode, 'debug')
