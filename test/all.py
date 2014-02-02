from test.framework import Test, TestTree
import time

def delme(x):
    def f():
        if x:
            raise Exception("failed")
    return f

def long():
    time.sleep(10)

tests = TestTree({
    'delme1': Test(delme(False)),
    'delme2': Test(delme(True)),
    'delme3': Test(delme(False)),
    'long1': Test(long, timeout=5),
    'long2': Test(long, timeout=5),
    'long3': Test(long, timeout=5),
    'long4': Test(long, timeout=5)
})
