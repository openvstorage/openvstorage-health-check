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
    """
    Severities for Open vStorage healthcheck results
    """
    # Value -1 means ignore this severity type for json/unattended logging
    error = type('ErrorSeverity', (), {'print_value': 'FAILED', 'value': 3, 'color': '\033[91m', 'type': 'error'})
    success = type('SuccessSeverity', (), {'print_value': 'SUCCESS', 'value': 1, 'color': '\033[92m', 'type': 'success'})
    debug = type('DebugSeverity', (), {'print_value': 'DEBUG', 'value': -1, 'color': '\033[94m', 'type': 'debug'})
    info = type('InfoSeverity', (), {'print_value': 'INFO', 'value': -1, 'color': '\033[94m', 'type': 'info'})
    skip = type('SkipSeverity', (), {'print_value': 'SKIPPED', 'value': 0, 'color': '\033[95m', 'type': 'skip'})
    exception = type('ExceptionSeverity', (), {'print_value': 'EXCEPTION', 'value': 4, 'color': '\033[91m', 'type': 'exception'})
    warning = type('WarningSeverity', (), {'print_value': 'WARNING', 'value': 2, 'color': '\033[93m', 'type': 'warning'})
    # custom = type('CustomSeverity', (), {'print_value': 'CUSTOM', 'value': 0, 'color': '\033[94m', 'type': 'custom'})

    @staticmethod
    def get_severity_types():
        return [attr for attr in dir(Severity) if not (attr.startswith("__") or inspect.isfunction(getattr(Severity, attr)))]

    @staticmethod
    def get_severities():
        return [value for attr, value in vars(Severity).iteritems() if not (attr.startswith("__") or inspect.isfunction(getattr(Severity, attr)))]

    @staticmethod
    def get_severity_by_print_value(print_value):
        for attr, value in vars(Severity).iteritems():
            if not (attr.startswith("__") or inspect.isfunction(getattr(Severity, attr))) and value.print_value == print_value:
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
        for severity in Severity.get_severities():
            self.counters[severity.print_value] = 0

        # Result of healthcheck in dict form
        self.result_dict = {}

    def _call(self, message, test_name, code, log_type, custom_value=None):
        """
        Process a message with a certain short test_name and type error message
        :param message: Log message for attended run
        :type message: str
        :param test_name: name for monitoring output
        :param code: error code
        :type code: str
        :param log_type:
            * 'error'
            * 'success'
            * 'debug'
            * 'info'
            * 'skip'
            * 'exception'
            * 'warning'
        :type log_type: str
        :param custom_value: a custom value that will be added when the error_message = custom
        :param custom_value: object
        :return:
        """
        severity = getattr(Severity, log_type)
        print_value = severity.print_value
        if test_name is not None:
            if severity.value != -1:
                # Enable custom error type:
                if test_name not in self.result_dict:
                    empty_messages = sorted([(sev.type, []) for sev in Severity.get_severities() if sev.value != -1])
                    # noinspection PyArgumentList
                    self.result_dict[test_name] = {"state": print_value,
                                                   'messages': collections.OrderedDict(empty_messages)}
                messages = self.result_dict[test_name]['messages']
                if print_value == 'CUSTOM':
                    messages[log_type].append({'code': code, 'message': custom_value})
                else:
                    messages[log_type].append({'code': code, 'message': message})
                result_severity = Severity.get_severity_by_print_value(self.result_dict[test_name]['state'])
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
        self._call(msg, test_name, code, log_type='error', )

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
        self._call(msg, test_name, code, log_type='success')

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
        self._call(msg, test_name, code, log_type='warning')

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
        self._call(msg, test_name, code, log_type='info')

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
        self._call(msg, test_name, code, log_type='exception')

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
        self._call(msg, test_name, code, log_type='skip')

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
        self._call(msg, test_name, code, log_type='debug')

    def custom(self, msg, test_name=None, value=None, code=ErrorCodes.default.error_code):
        """
        Report a custom log. The value will determine the tag
        :param msg: Log message for attended run
        :type msg: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param value: Value added to the log
        :type value: str
        :param code: error code
        :type code: str
        :return:
        """

        self._call(msg, test_name, code, log_type='custom', custom_value=value)
