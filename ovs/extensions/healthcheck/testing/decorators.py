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
from ovs.extensions.healthcheck.decorators import ensure_single_with_callback_cluster
from ovs.extensions.healthcheck.decorators import ensure_single_with_callback_local


class ClusterCheckTester(unittest.TestCase):

    def setUp(self):
        self.concurreny_amount = 5
        self.threads = []
        self.shared = {'callbacks': {}}
        for index in xrange(self.concurreny_amount):
            thread_object = {'called': False}
            self.shared[index] = thread_object
            self.threads.append(ClusterCheckTester.start_thread(ClusterCheckTester.thread_for_testing, 'test_{}'.format(index), args=(index,), kwargs={'thread_object': self.shared}))

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
        thread_object['callbacks'][time.time()] = 'Called'

    @staticmethod
    @ensure_single_with_callback_cluster(key='ovs_healthcheck_unit_testing', callback=concurrency_callback)
    def thread_for_testing(thread_index, thread_object):
        time.sleep(1)
        thread_object[thread_index]['called'] = True

    def test_concurrency(self):
        for thread in self.threads:
            if thread.isAlive():
                thread.join()
        # Start all threads
        self.assertEqual(len(self.threads), self.concurreny_amount)
        self.assertEqual(len(self.shared['callbacks'].keys()), self.concurreny_amount - 1)


class LocalCheckTester(unittest.TestCase):
    def setUp(self):
        self.concurreny_amount = 5
        self.threads = []
        self.shared = {'callbacks': {}}
        for index in xrange(self.concurreny_amount):
            thread_object = {'called': False}
            self.shared[index] = thread_object
            self.threads.append(ClusterCheckTester.start_thread(ClusterCheckTester.thread_for_testing, 'test_{}'.format(index),args=(index,), kwargs={'thread_object': self.shared}))

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
    def concurrency_callback(_, thread_object):
        thread_object['callbacks'][time.time()] = 'Called'

    @staticmethod
    @ensure_single_with_callback_local(key='ovs_healthcheck_unit_testing', callback=concurrency_callback)
    def thread_for_testing(thread_index, thread_object):
        time.sleep(1)
        thread_object[thread_index]['called'] = True

    def test_concurrency(self):
        for thread in self.threads:
            if thread.isAlive():
                thread.join()
        # Start all threads
        self.assertEqual(len(self.threads), self.concurreny_amount)
        self.assertEqual(len(self.shared['callbacks'].keys()), self.concurreny_amount - 1)


def suite():
    """
    Gather all the tests from this module in a test suite.
    """
    test_suite = unittest.TestSuite()
    test_suite.addTest(unittest.makeSuite(ClusterCheckTester))
    test_suite.addTest(unittest.makeSuite(LocalCheckTester))
    return test_suite
