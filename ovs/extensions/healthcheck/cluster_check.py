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
from functools import wraps
from ovs.extensions.healthcheck.result import HCResults
from ovs.extensions.generic.volatilemutex import volatile_mutex, NoLockAvailableException


def ensure_single_with_callback(key, callback=None):
    """
    Ensure only a single execution of the method
    """
    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            _mutex = volatile_mutex(key)
            try:
                _mutex.acquire(wait=0.005)
                return func(*args, **kwargs)
            except NoLockAvailableException:
                if callback is None:
                    return
                else:
                    if isinstance(callback, staticmethod):
                        return callback.__func__(*args, **kwargs)
                    else:
                        return callback(*args, **kwargs)
            finally:
                _mutex.release()
        return wrapped
    return wrapper


def cluster_check(func):
    """
    Decorator to separate cluster checks
    :return:
    """

    def set_result_success(*args, **kwargs):
        """
        :return:
        """
        arguments = args + (tuple(kwargs.values()))
        result_handler = None
        for arg in arguments:
            if isinstance(arg, HCResults.HCResultCollector):
                result_handler = arg
                break
        if result_handler is not None:
            result_handler.success('Call is being executed by {0}'.format('another storagerouter'))

    @wraps(func)
    @ensure_single_with_callback('ovs-healthcheck_{0}'.format(func.__name__), callback=set_result_success)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapped
