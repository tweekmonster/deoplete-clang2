import os
import sys
import logging
import unittest

if 'VERBOSE' in os.environ:
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    log.addHandler(handler)

from . import scan


class ScanTestHelper(unittest.TestCase):
    def assertBraceClose(self, sample, expect, msg=None):
        i = scan.find_boundary(sample)
        if i != -1:
            sample = sample[:i] + '[' + sample[i:] + ']'
        self.assertEqual(expect, sample, msg)


class TestObjCScan(ScanTestHelper):
    # Note: Whitespace is insignificant and only matters for separating
    # arguments.  There isn't a need to test newlines.

    def test_simple(self):
        self.assertBraceClose(
            'obj method',
            '[obj method]',
            'simple closing')

        self.assertBraceClose(
            'obj method:arg',
            '[obj method:arg]',
            'simple closing w/ argument')

        self.assertBraceClose(
            'obj method:arg second:arg',
            '[obj method:arg second:arg]',
            'simple multi-argument')

        self.assertBraceClose(
            'obj obj method:arg second:arg',
            'obj [obj method:arg second:arg]',
            'simple ambiguous atoms')

    def test_type_cast(self):
        self.assertBraceClose(
            '(NSObject *)obj method',
            '[(NSObject *)obj method]',
            'obj type cast')

        self.assertBraceClose(
            '(NSObject *)obj (NSObject *)method',
            '(NSObject *)obj (NSObject *)method',
            'incorrect type cast method')

        self.assertBraceClose(
            'obj method: (NSString *)arg',
            '[obj method: (NSString *)arg]',
            'type cast arg')

        self.assertBraceClose(
            '(NSObject *)obj method: (NSString *)arg',
            '[(NSObject *)obj method: (NSString *)arg]',
            'obj type cast and type cast arg')

        self.assertBraceClose(
            'obj method: (void *)(NSString *)arg',
            '[obj method: (void *)(NSString *)arg]',
            'double type cast arg')

        self.assertBraceClose(
            '(NSString *)[NSString alloc] init',
            '[(NSString *)[NSString alloc] init]',
            'type cast method call')

        self.assertBraceClose(
            '(id)@"text" method:arg method:arg',
            '[(id)@"text" method:arg method:arg]',
            'literal type cast')

    def test_assignment(self):
        self.assertBraceClose(
            'NSString s = [NSString alloc] init',
            'NSString s = [[NSString alloc] init]',
            'simple assignment')

        self.assertBraceClose(
            'NSString s = [[NSString alloc] init]',
            'NSString s = [[NSString alloc] init]',
            'left side of assignment not enclosed')

    def test_complicated(self):
        # Note: Detecting nested unclosed methods is not practical.  But, a
        # value followed by another value can be seen as not being an argument
        # for the parent method.
        self.assertBraceClose(
            '(id)@"str" arg1:(void *)val1 arg2:val2 val2arg',
            '(id)@"str" arg1:(void *)val1 arg2:[val2 val2arg]',
            'trailing value')

        self.assertBraceClose(
            '(id)@"str" arg1:(void *)val1 arg2:[val2 val2arg]',
            '[(id)@"str" arg1:(void *)val1 arg2:[val2 val2arg]]',
            'trailing method')

        self.assertBraceClose(
            '(id)@"str" arg1:(void *)val1 arg2:[val2 val2arg] val2argarg',
            '(id)@"str" arg1:(void *)val1 arg2:[[val2 val2arg] val2argarg]',
            'double trailing method')

    def test_semicolon(self):
        self.assertBraceClose(
            'obj1 obj2 method:arg second:arg;',
            'obj1 obj2 method:arg second:arg;',
            'simple semicolon stop at end')

        self.assertBraceClose(
            'obj1 obj2 method:arg; second:arg',
            'obj1 obj2 method:arg; second:arg',
            'simple semicolon stop before last arg')

        self.assertBraceClose(
            'obj1 obj2; method:arg second:arg',
            'obj1 obj2; method:arg second:arg',
            'simple semicolon stop before first arg')

        self.assertBraceClose(
            'obj1; obj2 method:arg second:arg',
            'obj1; [obj2 method:arg second:arg]',
            'simple semicolon stop before second obj')


if __name__ == "__main__":
    unittest.main()
