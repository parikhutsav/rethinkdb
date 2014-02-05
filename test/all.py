from test.framework import Test, TestTree, SimpleTest
import time
import test.common.unit
import sys

def dummy(x):
    def f():
        if x:
            raise Exception("failed")
    return f

def wait():
    time.sleep(2)

tests = TestTree({
    'dummy': TestTree({
        'pass': SimpleTest(dummy(False)),
        'fail': SimpleTest(dummy(True)),
        'timeout': SimpleTest(wait, timeout=1),
        'notimeout': SimpleTest(wait),
        'print': SimpleTest(lambda: sys.stdout.write('hello\n'))
    }),
    'unit': test.common.unit.AllUnitTests()
})
