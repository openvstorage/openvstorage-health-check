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
import time
import threading
import unittest
import uuid
from ovs.extensions.healthcheck.decorators import ensure_single_with_callback


class CheckTester(unittest.TestCase):

    def tearDown(self):
        for thread in self.threads:
            if thread.isAlive():
                thread.join()

    @staticmethod
    def start_thread(target, name, args=(), kwargs=None):
        if kwargs is None:
            kwargs = {}
        thread = threading.Thread(target=target, args=tuple(args), kwargs=kwargs)
        thread.setName(str(name))
        thread.start()
        return thread

    @staticmethod
    def concurrency_callback(*args, **kwargs):
        thread_object = kwargs.get('thread_object')
        thread_object['callbacks'][str(uuid.uuid4())] = 'Called at {0}'.format(time.time())

    @staticmethod
    @ensure_single_with_callback(key='ovs_healthcheck_unit_testing', callback=concurrency_callback, lock_type='cluster')
    def thread_for_testing_cluster(thread_index, thread_object, sleep_time=2):
        time.sleep(sleep_time)
        thread_object[thread_index]['called'] = True

    @staticmethod
    @ensure_single_with_callback(key='ovs_healthcheck_unit_testing', callback=concurrency_callback, lock_type='local')
    def thread_for_testing_local(thread_index, thread_object, sleep_time=2):
        time.sleep(sleep_time)
        thread_object[thread_index]['called'] = True

    def test_concurrency_local(self):
        concurreny_amount = 5
        self.threads = []
        shared = {'callbacks': {}}
        for index in xrange(concurreny_amount):
            thread_object = {'called': False}
            shared[index] = thread_object
            self.threads.append(CheckTester.start_thread(CheckTester.thread_for_testing_local, 'test_{}'.format(index), args=(index,), kwargs={'thread_object': shared}))
        for thread in self.threads:
            if thread.isAlive():
                thread.join()
        # Start all threads
        self.assertEqual(len(shared['callbacks'].keys()), concurreny_amount - 1)

    def test_concurrency_cluster(self):
        concurreny_amount = 5
        self.threads = []
        shared = {'callbacks': {}}
        for index in xrange(concurreny_amount):
            thread_object = {'called': False}
            shared[index] = thread_object
            self.threads.append(CheckTester.start_thread(CheckTester.thread_for_testing_cluster, 'test_{}'.format(index), args=(index,), kwargs={'thread_object': shared}))
        for thread in self.threads:
            if thread.isAlive():
                thread.join()
        # Start all threads
        self.assertEqual(len(shared['callbacks'].keys()), concurreny_amount - 1)


def suite():
    """
    Gather all the tests from this module in a test suite.
    """
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(CheckTester))
    return test_suite
