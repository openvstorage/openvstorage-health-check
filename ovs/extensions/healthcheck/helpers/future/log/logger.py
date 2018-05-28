# Copyright (C) 2018 iNuron NV
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
Contains the Logger module
"""

import os
import sys
import copy
import time
import socket
import logging
import itertools


class LogFormatter(logging.Formatter):
    """
    Formatter for the logger
    """
    def formatTime(self, record, datefmt=None):
        """
        Overrides the default formatter to include UTC offset. Is only called for when the formatter has %(asctime)s in it
        :param record: Record to format
        :type record: logging.LogRecord
        :param datefmt: Date format to apply to the record. If omitted, ISO8601 is used
        :type datefmt: str
        :return: The formatted timestamp
        :rtype: str
        """
        _ = datefmt
        ct = self.converter(record.created)
        tz = time.altzone if time.daylight and ct.tm_isdst > 0 else time.timezone
        offset = '{0}{1:0>2}{2:0>2}'.format('-' if tz > 0 else '+', abs(tz) // 3600, abs(tz // 60) % 60)
        base_time = time.strftime('%Y-%m-%d %H:%M:%S', ct)
        return '{0} {1:03.0f}00 {2}'.format(base_time, record.msecs, offset)

    def format(self, record):
        """
        Format a LogRecord
        :param record: Record to format
        :type record: logging.LogRecord
        :return: Formatted record
        :rtype: str
        """
        if 'hostname' not in record.__dict__:
            record.hostname = socket.gethostname()
        if 'sequence' not in record.__dict__:
            record.sequence = Logger.counter.next()
        return super(LogFormatter, self).format(record)


class Logger(logging.Logger):
    """
    Logger class used for log messages invoked by OVS

    WARNING: This log handler might be highly unreliable if not used correctly. It can log to redis, but if Redis is
    not working as expected, it will result in lost log messages. If you want reliable logging, do not use Redis at all
    or log to files and have a separate process forward them to Redis (so logs can be re-send if Redis is unavailable)
    """
    TARGET_TYPE_FILE = 'file'
    TARGET_TYPE_REDIS = 'redis'
    TARGET_TYPE_CONSOLE = 'console'
    TARGET_TYPES = [TARGET_TYPE_FILE, TARGET_TYPE_REDIS, TARGET_TYPE_CONSOLE]

    LOG_PATH = '/var/log/ovs'
    LOG_LEVELS = {0: 'NOTSET',
                  10: 'DEBUG',
                  20: 'INFO',
                  30: 'WARNING',
                  40: 'ERROR',
                  50: 'CRITICAL'}

    counter = itertools.count()

    _logs = {}  # Used by unittests
    _cache = {}

    def __init__(self, name, forced_target_type=None, default_extra_log_params=None):
        # type: (str, str, dict) -> None
        """
        Initialize a logger instance
        :param name: Name of the logger instance
        :type name: str
        :param forced_target_type: Override the target type. Defaults to checking the context (stdout or file)
        :type forced_target_type: str
        :param default_extra_log_params: Default parameters to give with every log
        :type default_extra_log_params: dict
        """
        super(Logger, self).__init__(name.split('-')[0])
        self._full_name = name
        self._unittest_mode = os.environ.get('RUNNING_UNITTESTS') == 'True'

        if name in Logger._cache:
            handler = Logger._cache[name]
        else:
            handler = self.get_handler(forced_target_type=forced_target_type)

        self.setLevel(handler.level)
        self.handlers = [handler]
        self.extra_log_params = default_extra_log_params

    def get_handler(self, forced_target_type=None):
        """
        Retrieve a handler for the Logger instance
            * Create a handler
            * Set log level for the handler
            * Add a formatter to the handler

        The log level is configured on the logger instance AND on the handler
        The logger instance determines whether the LogRecord is 'important' enough.
            * If not, no handlers are used
            * If so, all handlers get the LogRecord, the handlers will then filter themselves based on the log level they have configured
        :param forced_target_type: Forcefully override the target type configured in configuration management or set in environment variables
        :type forced_target_type: str
        :return: The configured handler instance
        :rtype: logging.FileHandler|logging.StreamHandler|RedisListHandler
        """
        target_params = self._load_target_parameters(source=self.name, forced_target_type=forced_target_type, allow_override=True)
        log_level = target_params['level']
        target_type = target_params['type']

        # Create handler
        if target_type == Logger.TARGET_TYPE_FILE:
            handler = logging.FileHandler(target_params['filename'])
        else:
            handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(getattr(logging, log_level))
        handler.setFormatter(LogFormatter('%(asctime)s - %(hostname)s - %(process)s/%(thread)d - {0}/%(filename)s - %(funcName)s - %(sequence)s - %(levelname)s - %(message)s'.format(self._full_name)))
        Logger._cache[self._full_name] = handler
        return handler

    @classmethod
    def load_path(cls, source):
        """
        Load path to log to
        :param source: Name of the logger instance
        :return: Path on filesystem to log to
        :rtype: str
        """
        if cls.LOG_PATH is None:
            raise ValueError('LOG_PATH is not specified')

        log_filename = '{0}/{1}.log'.format(cls.LOG_PATH, source)
        if not os.path.exists(cls.LOG_PATH):
            os.mkdir(cls.LOG_PATH, 0777)
        if not os.path.exists(log_filename):
            open(log_filename, 'a').close()
            os.chmod(log_filename, 0o666)
        return log_filename

    @classmethod
    def get_sink_path(cls, source, forced_target_type=None):
        """
        Retrieve the path to sink logs to
        :param source: Source
        :type source: str
        :param forced_target_type: Override target type
        :type forced_target_type: str
        :return: The path to sink to
        :rtype: str
        """
        target_params = cls._load_target_parameters(source=source, forced_target_type=forced_target_type, allow_override=False)
        if target_params['type'] == cls.TARGET_TYPE_CONSOLE:
            return 'console:'
        elif target_params['type'] == cls.TARGET_TYPE_FILE:
            return target_params['filename']
        elif target_params['type'] == cls.TARGET_TYPE_REDIS:
            return 'redis://{0}:{1}{2}'.format(target_params['host'], target_params['port'], target_params['queue'])
        else:
            raise ValueError('Invalid target type specified')

    @classmethod
    def get_logging_info(cls):
        """
        Retrieve logging information from the Configuration management
        Should be inherited
        :return: Logging information retrieved from the configuration management
        :rtype: dict
        """
        return {'type': 'console', 'level': 'info'}  # Should be overruled by classes inheriting from this 1

    @classmethod
    def _load_target_parameters(cls, source, forced_target_type, allow_override):
        """
        Based on the calculated 'target_type', a dictionary structure is created with additional information related to the 'target_type'
        The target type is calculated in this order:
            1. Forced target type
            2. OS environment variable
            3. Configured in configuration management
            4. Default value (console)
        Additional information about how to configure the target_type
            * Possible values for the target type: ['file', 'console', 'redis']
            * Target type can be configured:
                * By setting environment variable in current process: OVS_LOGTYPE_OVERRIDE
                * By setting 'type' in configuration management key '/ovs/framework/logging'. E.g.: {"type": "console"}
            * Target type can be enforced by executing Logger(name='my_log_name', forced_target_type='console')

        :param source: Name of the logger, only applicable for target_type 'file' and 'redis'
        :type source: str
        :param allow_override: Allow to override the target type
        :type allow_override: bool
        :param forced_target_type: Forcefully override the target type configured in configuration management or set in environment variables
        :type forced_target_type: str
        :return: Information about target type, log level and other relevant information related to the target type
        :rtype: dict
        """
        log_info = cls.get_logging_info()
        log_level = log_info.get('level', 'debug').upper()
        if allow_override is True:
            target_type = forced_target_type or os.environ.get('OVS_LOGTYPE_OVERRIDE') or log_info.get('type') or cls.TARGET_TYPE_CONSOLE
        else:
            target_type = forced_target_type or log_info.get('type') or cls.TARGET_TYPE_CONSOLE

        if target_type not in cls.TARGET_TYPES:
            raise ValueError('Invalid target type specified: {0}'.format(target_type))
        if log_level not in cls.LOG_LEVELS.values():
            raise ValueError('Invalid log level specified: {0}'.format(log_level))

        if target_type == cls.TARGET_TYPE_FILE:
            return {'type': cls.TARGET_TYPE_FILE,
                    'level': log_level,
                    'filename': cls.load_path(source)}

        if target_type == cls.TARGET_TYPE_REDIS:
            queue = log_info.get('queue', '/ovs/logging')
            if '{0}' in queue:
                queue = queue.format(source)
            return {'type': cls.TARGET_TYPE_REDIS,
                    'level': log_level,
                    'queue': '/{0}'.format(queue.lstrip('/')),
                    'host': log_info.get('host', 'localhost'),
                    'port': log_info.get('port', 6379)}

        return {'type': cls.TARGET_TYPE_CONSOLE,
                'level': log_level}

    def _log(self, level, msg, args, exc_info=None, extra=None):
        """
        Log pass-through
        """
        if self._unittest_mode is True:
            if self.name not in Logger._logs:
                Logger._logs[self.name] = {}
            Logger._logs[self.name][msg.strip()] = Logger.LOG_LEVELS[level]

        if self.extra_log_params or extra:
            total_extra = copy.deepcopy(self.extra_log_params or {})
            total_extra.update(extra or {})
            if total_extra.pop('print_msg', None):
                print msg

        super(Logger, self)._log(level, msg, args, exc_info=exc_info, extra=extra)
