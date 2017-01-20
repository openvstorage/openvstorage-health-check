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
import inspect
import collections
from ovs.extensions.healthcheck.config.error_codes import ErrorCodes


class Severity(object):
    def __init__(self, print_value, value, severity_type, color):
        self.print_value = print_value
        self.value = value
        self.type = severity_type
        self.color = color


class Severities(object):
    """
    Severities for Open vStorage healthcheck results
    """
    # Value -1 means ignore this severity type for json/unattended logging
    error = Severity('FAILED', 3, 'error', '\033[91m')
    success = Severity('SUCCESS', 1, 'success', '\033[92m')
    debug = Severity('DEBUG', -1, 'debug', '\033[94m')
    info = Severity('INFO', -1, 'info', '\033[94m')
    skip = Severity('SKIPPED', 0, 'skip', '\033[95m')
    exception = Severity('EXCEPTION', 4, 'exception', '\033[91m')
    warning = Severity('WARNING', 2, 'warning', '\033[93m')

    @staticmethod
    def get_severity_types():
        return [attr for attr in dir(Severities) if not (attr.startswith("__") or inspect.isfunction(getattr(Severities, attr)))]

    @staticmethod
    def get_severities():
        return [value for attr, value in vars(Severities).iteritems() if not (attr.startswith("__") or inspect.isfunction(getattr(Severities, attr)))]

    @staticmethod
    def get_severity_by_print_value(print_value):
        for attr, value in vars(Severities).iteritems():
            if not (attr.startswith("__") or inspect.isfunction(getattr(Severities, attr))) and value.print_value == print_value:
                return value


class HCResults(object):
    """
    Open vStorage Log Handler
    """
    # Statics
    MODULE = "helper"
    # Log types that need to be replaced before logging to file
    LOG_CHANGING = {
        "success": "info",
        "skip": "info",
        "custom": "info"
    }
    LINE_COLOR = '\033[0m'

    def __init__(self, unattended=False, to_json=False):
        """
        Init method
        :param unattended: unattended output
        :type unattended: bool
        :param to_json: json output
        :type to_json: bool
        """
        self.unattended = unattended
        self.to_json = to_json

        self.print_progress = not(to_json or unattended)
        # Setup HC counters
        self.counters = {}
        for severity in Severities.get_severities():
            self.counters[severity.print_value] = 0

        # Result of healthcheck in dict form
        self.result_dict = {}

    def _call(self, message, test_name, code, severity):
        """
        Process a message with a certain short test_name and type error message
        :param message: Log message for attended run
        :type message: str
        :param test_name: name for monitoring output
        :param code: error code
        :type code: str
        :param severity: Severity object
        :type severity: ovs.extensions.healthcheck.result.Severity
        :return:
        """
        print_value = severity.print_value
        if test_name is not None:
            if severity.value != -1:
                # Enable custom error type:
                if test_name not in self.result_dict:
                    empty_messages = sorted([(sev.type, []) for sev in Severities.get_severities() if sev.value != -1])
                    # noinspection PyArgumentList
                    self.result_dict[test_name] = {"state": print_value,
                                                   'messages': collections.OrderedDict(empty_messages)}
                messages = self.result_dict[test_name]['messages']
                messages[severity.type].append({'code': code, 'message': message})
                result_severity = Severities.get_severity_by_print_value(self.result_dict[test_name]['state'])
                if severity.value > result_severity.value:
                    self.result_dict[test_name]['state'] = print_value
                self.result_dict[test_name]["messages"] = messages
        self.counters[print_value] += 1
        if self.print_progress:
            print "{0}[{1}] {2}{3}".format(severity.color, print_value, self.LINE_COLOR, str(message))

    def get_results(self):
        """
        Prints the result for check_mk
        :return: results
        :rtype: dict
        """
        excluded_messages = ['INFO', 'DEBUG']
        if self.unattended:
                for key, value in sorted(self.result_dict.items(), key=lambda x: x[0]):
                    if value not in excluded_messages:
                            print "{0} {1}".format(key, value["state"])
        if self.to_json:
            import json
            print json.dumps(self.result_dict, indent=4)
        return self.result_dict

    def failure(self, msg, test_name=None, code=ErrorCodes.default.error_code):
        """
        Report a failure log
        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param code: error code
        :type code: str
        :return:
        """
        self._call(msg, test_name, code, severity=Severities.error)

    def success(self, msg, test_name=None, code=ErrorCodes.default.error_code):
        """
        Report a success log
        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param code: error code
        :type code: str
        :return:
        """
        self._call(msg, test_name, code, severity=Severities.success)

    def warning(self, msg, test_name=None, code=ErrorCodes.default.error_code):
        """
        Report a warning log
        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param code: error code
        :type code: str
        :return:
        """
        self._call(msg, test_name, code, severity=Severities.warning)

    def info(self, msg, test_name=None, code=ErrorCodes.default.error_code):
        """
        Report a info log
        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param code: error code
        :type code: str
        :return:
        """
        self._call(msg, test_name, code, severity=Severities.info)

    def exception(self, msg, test_name=None, code=ErrorCodes.default.error_code):
        """
        Report a exception log
        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param code: error code
        :type code: str
        :return:
        """
        self._call(msg, test_name, code, severity=Severities.exception)

    def skip(self, msg, test_name=None, code=ErrorCodes.default.error_code):
        """
        Report a skipped log
        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param code: error code
        :type code: str
        :return:
        """
        self._call(msg, test_name, code, severity=Severities.skip)

    def debug(self, msg, test_name=None, code=ErrorCodes.default.error_code):
        """
        Report a debug log
        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param code: error code
        :type code: str
        :return:
        """
        self._call(msg, test_name, code, severity=Severities.debug)
