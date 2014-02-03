from multiprocessing import Process, Semaphore
from threading import Thread
import signal
import test.common.vcoptparse

def run(all_tests, args):
    filter = TestFilter.parse(args)
    tests = all_tests.filter(filter)
    filter.check_use()
    testrunner = TestRunner(tests, tasks=3)
    testrunner.run()

class TestRunner():
    def __init__(self, tests, tasks=1, timeout=600):
        self.tests = tests
        self.semaphore = Semaphore(tasks)
        self.processes = []
        self.timeout = timeout
        
    def run(self):
        for name, test in self.tests:
            process = TestProcess(self, name, test)
            self.processes += [process]
            process.start()
        for process in self.processes:
            process.join()

class TestProcess():
    def __init__(self, runner, name, test):
        self.runner = runner
        self.name = name
        self.test = test
        self.timeout = test.timeout() or runner.timeout
        self.supervisor = None
        self.process = None

    def start(self):
        self.supervisor = Thread(target=self.supervise,
                                 name="supervisor:"+self.name)
        self.supervisor.start()

    def run(self):
        with Timeout(self.timeout):
            try:
                self.test.run()
            except TimeoutException:
                print "Test timed out:", self.name
            except Exception as e:
                print "Test failed:", self.name, e
            else:
                print "Test passed:", self.name

    def supervise(self):
        with self.runner.semaphore:
            self.process = Process(target=self.run,
                                   name="process:"+self.name)
            self.process.start()
            self.process.join(self.timeout + 5)
            if self.process.is_alive():
                print "Terminating test:", self.name
                self.process.terminate()

    def join(self):
        self.supervisor.join()

class TimeoutException(Exception):
    pass
        
class Timeout:
    def __init__(self, seconds):
        self.timeout = seconds

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.alarm)
        signal.alarm(self.timeout)

    def __exit__(self, type, exception, trace):
        signal.alarm(0)

    @staticmethod
    def alarm(*ignored):
        raise TimeoutException()
        
class TestFilter:
    INCLUDE = 'INCLUDE'
    EXCLUDE = 'EXCLUDE'

    def __init__(self, default=EXCLUDE):
        self.default = default
        self.tree = {}
        self.was_matched = False

    @classmethod
    def parse(self, args):
        if not args:
            return TestFilter(self.INCLUDE)
        filter = TestFilter()
        for arg in args:
            if arg[0] == '!':
                arg = arg[1:]
                type = self.EXCLUDE
            else:
                type = self.INCLUDE
            filter.at(arg.split('.')).reset(type)
        return filter

    def at(self, path):
        if not path:
            return self
        else:
            return self.zoom(path[0], create=True).at(path[1:])

    def reset(self, type=EXCLUDE):
        self.default = type
        self.tree = {}

    def match(self):
        self.was_matched = True
        return self.default == self.INCLUDE

    def zoom(self, name, create=False):
        try:
            return self.tree[name]
        except KeyError:
            subfilter = TestFilter(self.default)
            if create:
                self.tree[name] = subfilter
                return subfilter
        
    def check_use(self, path=[]):
        if not self.was_matched:
            raise Exception('No such test %s' % '.'.join(path))
        for name, filter in self.tree.iteritems():
            filter.check_use(path + [name])

    def __repr__(self):
        return ("TestFilter(" + self.default + ", " + repr(self.was_matched) +
                ", " + repr(self.tree) + ")")

    def all_same(self):
        self.was_matched = True
        return not self.tree
            
class Test:
    def __init__(self, run=None, timeout=None):
        self._run = run
        self._timeout = timeout

    def run(self):
        self._run()

    def filter(self, filter):
        if filter.match():
            return self
        else:
            return None

    def __iter__(self):
        yield (None, self)

    def timeout(self):
        return self._timeout
        
class TestTree(Test):
    def __init__(self, tests={}):
        self.tests = dict(tests)

    def filter(self, filter):
        if filter.all_same():
            if filter.match():
                return self
            else:
                return trimmed
        trimmed = TestTree()
        for name, test in self.tests.iteritems(): 
            subfilter = filter.zoom(name)
            trimmed[name] = test.filter(subfilter)
        return trimmed

    def run(self):
        for test in self.tests.values():
            test.run()

    def __getitem__(self, name):
        return self.tests[name]

    def __setitem__(self, name, test):
        if not test or (isinstance(test, TestTree) and not test.tests):
            try:
                del(self.tests[name])
            except KeyError:
                pass
        else:
            self.tests[name] = test
                
    def __iter__(self):
        for name in sorted(self.tests.keys()):
            for subname, test in self.tests[name]:
                if subname:
                    yield (name + '.' + subname, test)
                else:
                    yield name, test

