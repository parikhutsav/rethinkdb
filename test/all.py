from test.framework import Test, TestTree
import time
import test.unit

def delme(x):
    def f():
        if x:
            raise Exception("failed")
    return f

def wait():
    time.sleep(2)

tests = TestTree({
    'dummy': TestTree({
        'pass': Test(delme(False)),
        'fail': Test(delme(True)),
        'timeout': Test(wait, timeout=1),
        'notimeout': Test(wait),
    }),
    'unit': test.common.unit.UnitTests()
})
