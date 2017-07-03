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
import time
from functools import wraps
from ovs_extensions.generic.filemutex import file_mutex
from ovs_extensions.generic.filemutex import NoLockAvailableException as NoFileLockAvailableException
from ovs.extensions.generic.system import System
from ovs.extensions.generic.volatilemutex import volatile_mutex
from ovs.extensions.generic.volatilemutex import NoLockAvailableException as NoVolatileLockAvailableException
from ovs.extensions.healthcheck.helpers.cache import CacheHelper
from ovs.extensions.healthcheck.result import HCResults


def ensure_single_with_callback(key, callback=None, lock_type='local'):
    """
    Ensure only a single execution of the method
    The cluster check could have some raceconditions when the following conditions are met:
    - Decorated method takes longer than 60s (volatilemutex limit is 60s) (memcache is unstable in keeping data);
    - The second acquire enters the callback and fetches the key from memcache while the key has not been set by the first (see below for fix).
    """
    def wrapper(func):
        @wraps(func)
        def wrapped(*args, **kwargs):
            if lock_type == 'local':
                _mutex = file_mutex(key)
            elif lock_type == 'cluster':
                _mutex = volatile_mutex(key)
            else:
                raise ValueError('Lock type {0} is not supported!'.format(lock_type))
            try:
                _mutex.acquire(wait=0.005)
                local_sr = System.get_my_storagerouter()
                CacheHelper.set(key=key, item={'ip': local_sr.ip, 'hostname': local_sr.name}, expire_time=60)
                return func(*args, **kwargs)
            except (NoFileLockAvailableException, NoVolatileLockAvailableException):
                if callback is None:
                    return
                else:
                    executor_info = None
                    start = time.time()
                    while executor_info is None:
                        # Calculated guesswork. If a callback function would be expected, the acquire has happened for another executor  the volatilekey should be set eventually
                        # However by setting it after the acquire, the callback executor and original method executor can race between fetch and set
                        # A better implementation would be relying on the fwk ensure_single_decorator as they check for various races themselves
                        # This is just a poor mans, temporary implementation
                        if start - time.time() > 5:
                            raise ValueError('Timed out after 5 seconds while fetching the information about the executor.')
                        try:
                            executor_info = CacheHelper.get(key=key)
                        except:
                            pass
                    callback_func = callback.__func__ if isinstance(callback, staticmethod) else callback
                    argnames = inspect.getargspec(callback_func)[0]
                    arguments = list(args)
                    kwargs.update({'test_name': func.__name__})
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

    @ensure_single_with_callback('ovs-healthcheck_cluster_wide_{0}'.format(func.__name__), callback=set_result_success, lock_type='cluster')
    @wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapped


def node_check(func):
    """
    Decorator to only run a check on a node once and provide a callback for the others
    :param func:
    :return:
    """
    def set_result_success(test_name, result_handler, *args, **kwargs):
        """
        :return:
        """
        result_handler.success('Test {0} is already being executed on this node.'.format(test_name))

    @ensure_single_with_callback('ovs-healthcheck_node_wide_{0}'.format(func.__name__), callback=set_result_success, lock_type='local')
    @wraps(func)
    def wrapped(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapped
