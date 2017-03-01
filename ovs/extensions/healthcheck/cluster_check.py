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
import inspect
from functools import wraps
from ovs.extensions.healthcheck.helpers.cache import CacheHelper
from ovs.extensions.healthcheck.result import HCResults
from ovs.extensions.generic.system import System
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
                local_sr = System.get_my_storagerouter()
                CacheHelper.set(key=key, item={'ip': local_sr.ip, 'hostname': local_sr.name}, expire_time=60)
                return func(*args, **kwargs)
            except NoLockAvailableException:
                if callback is None:
                    return
                else:
                    callback_func = callback.__func__ if isinstance(callback, staticmethod) else callback
                    argnames, _, _, _ = inspect.getargspec(callback_func)
                    executor_info = CacheHelper.get(key=key)
                    arguments = list(args)
                    if executor_info is not None:
                        kwargs.update(executor_info)
                        if 'result_handler' in argnames:
                            result_handler = kwargs.get('result_handler')
                            for index, arg in enumerate(arguments):
                                if isinstance(arg, HCResults.HCResultCollector):
                                    result_handler = arguments.pop(index)
                                    break
                            if result_handler is None:
                                raise TypeError('Expected an instance of {}'.format(type(HCResults.HCResultCollector)))
                            kwargs['result_handler'] = result_handler
                    return callback_func(*tuple(arguments), **kwargs)
            finally:
                _mutex.release()
        return wrapped
    return wrapper


def cluster_check(func):
    """
    Decorator to separate cluster checks
    :return:
    """
    def set_result_success(ip, hostname, result_handler, *args, **kwargs):
        """
        :return:
        """
        result_handler.success('Call is being executed by {0} - {1}.'.format(hostname, ip))

    @wraps(func)
    @ensure_single_with_callback('ovs-healthcheck_{0}'.format(func.__name__), callback=set_result_success)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapped
