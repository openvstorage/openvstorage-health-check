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
from ovs.extensions.healthcheck.config.error_codes import ErrorCode, ErrorCodes


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

    class HCResultCollector(object):
        """
        Result collector object. Forwards all calls to the HCResults instances stored within
        Usage is to keep the HCResults unmodified while adjusting the test name for every test
        """
        def __init__(self, result, test_name):
            """
            Initialize this subclass
            :param result: Instance of HCResults
            :type result: HCResults
            :param test_name: test name to be added to the results
            :type test_name: str
            """
            self._result = result
            self._test_name = test_name

        def __getattr__(self, item):
            """
            Get attribute. This method should point to the method of the parent (HCResults instance)
            :param item: item to get (method from HCResults)
            :type item: str
            :return: method of HCResults
            :rtype: method
            """
            return lambda *args, **kwargs: getattr(self._result, item)(test_name=self._test_name, *args, **kwargs)

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

    def _call(self, add_to_result, message, code, severity, test_name=''):
        """
        Process a message with a certain short _test_name and type error message
        :param add_to_result: Add the item to the internal result collection
        :type add_to_result: bool
        :param message: Log message for attended run
        :type message: str
        :param test_name: name for monitoring output
        :type test_name: str
        :param code: Error code
        :type code: str or ovs.extensions.healthcheck.config.error_codes.ErrorCode
        :param severity: Severity object
        :type severity: ovs.extensions.healthcheck.result.Severity
        :return:
        """
        if isinstance(code, ErrorCode):
            code = code.error_code
        print_value = severity.print_value
        if add_to_result is True and test_name:
            if severity.value != -1:
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
            print json.dumps(self.result_dict, indent=4, sort_keys=True)
        return self.result_dict

    def failure(self, msg, add_to_result=True, code=ErrorCodes.default, **kwargs):
        """
        Report a failure log
        :param msg: Log message for attended run
        :type msg: str
        :param add_to_result: name for monitoring output
        :type add_to_result: bool
        :param code: error code
        :type code: str
        :return:
        """
        self._call(message=msg, add_to_result=add_to_result, code=code, severity=Severities.error, **kwargs)

    def success(self, msg, add_to_result=True, code=ErrorCodes.default, **kwargs):
        """
        Report a success log
        :param msg: Log message for attended run
        :type msg: str
        :param add_to_result: name for monitoring output
        :type add_to_result: bool
        :param code: error code
        :type code: str
        :return:
        """
        self._call(message=msg, add_to_result=add_to_result, code=code, severity=Severities.success, **kwargs)

    def warning(self, msg, add_to_result=True, code=ErrorCodes.default, **kwargs):
        """
        Report a warning log
        :param msg: Log message for attended run
        :type msg: str
        :param add_to_result: name for monitoring output
        :type add_to_result: bool
        :param code: error code
        :type code: str
        :return:
        """
        self._call(message=msg, add_to_result=add_to_result, code=code, severity=Severities.warning, **kwargs)

    def info(self, msg, add_to_result=True, code=ErrorCodes.default, **kwargs):
        """
        Report a info log
        :param msg: Log message for attended run
        :type msg: str
        :param add_to_result: name for monitoring output
        :type add_to_result: bool
        :param code: error code
        :type code: str
        :return:
        """
        self._call(message=msg, add_to_result=add_to_result, code=code, severity=Severities.info, **kwargs)

    def exception(self, msg, add_to_result=True, code=ErrorCodes.default, **kwargs):
        """
        Report a exception log
        :param msg: Log message for attended run
        :type msg: str
        :param add_to_result: name for monitoring output
        :type add_to_result: bool
        :param code: error code
        :type code: str
        :return:
        """
        self._call(message=msg, add_to_result=add_to_result, code=code, severity=Severities.exception, **kwargs)

    def skip(self, msg, add_to_result=True, code=ErrorCodes.default,  **kwargs):
        """
        Report a skipped log
        :param msg: Log message for attended run
        :type msg: str
        :param add_to_result: name for monitoring output
        :type add_to_result: bool
        :param code: error code
        :type code: str
        :return:
        """
        self._call(message=msg, add_to_result=add_to_result, code=code, severity=Severities.skip, **kwargs)

    def debug(self, msg, add_to_result=True, code=ErrorCodes.default, **kwargs):
        """
        Report a debug log
        :param msg: Log message for attended run
        :type msg: str
        :param add_to_result: name for monitoring output
        :type add_to_result: bool
        :param code: error code
        :type code: str
        :return:
        """
        self._call(message=msg, add_to_result=add_to_result, code=code, severity=Severities.debug, **kwargs)
