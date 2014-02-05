from multiprocessing import Process, Semaphore, Pipe
from threading import Thread, Lock
import signal
from argparse import ArgumentParser
import sys
from tempfile import mkdtemp
from os.path import abspath, join, dirname, pardir
from os import mkdir, dup2
import traceback
import subprocess

parser = ArgumentParser(description='Run RethinkDB tests')
parser.add_argument('-j', '--jobs', type=int, default=1,
                    help='The number of tests to run simultaneously')
parser.add_argument('-l', '--list', dest='mode', action='store_const', const='list')
parser.add_argument('-o', '--output-dir')
parser.add_argument('-r', '--repeat', type=int, default=1,
                    help='The number of times to repeat each test')
parser.add_argument('-k', '--continue', action='store_true', dest='kontinue',
                    help='Continue repeating even if a test fails')
parser.add_argument('-v', '--verbose', action='store_true')
parser.add_argument('-t', '--timeout', type=int, default=600,
                    help='Timeout in seconds for each test')
parser.add_argument('filter', nargs='*',
                    help='The name of the tests to run, of a group'
                    'of tests or their negation with !')

def run(all_tests, args):
    args = parser.parse_args(args)
    filter = TestFilter.parse(args.filter)
    tests = all_tests.filter(filter)
    reqs = tests.requirements()
    conf = configure(reqs)
    tests = tests.configure(conf)
    filter.check_use()
    if args.mode == 'list':
        for name, __ in tests:
            print name
        return
    else:
        testrunner = TestRunner(
            tests, conf,
            tasks=args.jobs,
            timeout=args.timeout,
            output_dir=args.output_dir,
            verbose=args.verbose,
            repeat=args.repeat,
            kontinue=args.kontinue)
        testrunner.run()

def configure(reqs):
    # TODO
   return dict(
       SRC_ROOT = abspath(join(dirname(__file__), pardir)))

def redirect_fd_to_file(fd, file, tee=False):
    if not tee:
        f = open(file, 'w')
    else:
        tee = subprocess.Popen(["tee", file], stdin=subprocess.PIPE)
        f = tee.stdin
    dup2(f.fileno(), fd)
    

class TestRunner():
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'
    TIMED_OUT = 'TIMED_OUT'
    STARTED = 'STARTED'
    
    def __init__(self, tests, conf, tasks=1, timeout=600, output_dir=None, verbose=False, repeat=1, kontinue=False):
        self.tests = tests
        self.semaphore = Semaphore(tasks)
        self.processes = []
        self.timeout = timeout
        self.conf = conf
        self.verbose = verbose
        self.repeat = repeat
        self.kontinue = kontinue
        self.failed_set = set()

        if output_dir:
            self.dir = output_dir
            try:
                mkdir(output_dir)
            except OSError as e:
                print >> sys.stderr, "Could not create output directory (" + output_dir + "):", e
                sys.exit(1)
        else:
            self.dir = mkdtemp('', 'test_results.', conf['SRC_ROOT'])
        
        self.running = Locked({})
        self.view = TermView(self) if sys.stdout.isatty() and not verbose else TextView(self)
        
    def run(self):
        print "Running %d tests (output_dir: %s)" % (len(self.tests), self.dir)

        for i in range(0, self.repeat):
            for name, test in self.tests: 
                if self.kontinue or name not in self.failed_set:
                    id = (name, i)
                    dir = join(self.dir, name if self.repeat == 1 else name + '.' + str(i+1))
                    process = TestProcess(self, id, test, dir)
                    with self.running as running:
                        running[id] = process
                    process.start()

        # loop through the remaining TestProcesses and wait for them to finish
        while True:
            with self.running as running:
                if not running:
                    break
                id, process = running.iteritems().next()
            process.join()
            with self.running as running:
                try: 
                    del(running[id])
                except KeyError:
                    pass
                else:
                    process.write_fail_message("Test failed to report success or"
                                               " failure status") 
                    self.tell(self.FAILED, id)

        self.view.close()

    def tell(self, status, id):
        name = id[0]
        if status != 'STARTED':
            with self.running as running:
                del(running[id])
            if status != 'SUCCESS':
                self.failed_set.add(name)
        self.view.tell(status, name)

    def count_running(self):
        with self.running as running:
            return len(running)

class TextView():
    green = "\033[32;1m"
    red = "\033[31;1m"
    nocolor = "\033[0m"
        
    def __init__(self, runner):
        self.runner = runner
        self.use_color = sys.stdout.isatty()

    def tell(self, event, name):
        if event != 'STARTED':
            print self.format_event(event, name)

    def format_event(self, str, name):
        short = dict(
            FAILED = (self.red, "FAIL"),
            SUCCESS = (self.green, "OK  "),
            TIMED_OUT = (self.red, "TIME")
        )[str]
        if self.use_color:
            return short[0] + short[1] + " " + name + self.nocolor
        else:
            return short[1] + " " + name

    def close(self):
        pass

class TermView(TextView):
    def __init__(self, runner):
        TextView.__init__(self, runner)
        self.running_count = 0
        self.buffer = ''
        self.read_pipe, self.write_pipe = Pipe(False)
        self.thread = Thread(target=self.run, name='TermView')
        self.thread.daemon = True
        self.thread.start()

    def tell(self, *args):
        self.write_pipe.send(args)

    def close(self):
        self.write_pipe.send('EXIT')
        self.thread.join()
        
    def run(self):
        while True:
            args = self.read_pipe.recv()
            if args == 'EXIT':
                break
            self.thread_tell(*args)
        
    def thread_tell(self, event, name):
        if event == 'STARTED':
            self.running_count += 1
            self.update_status()
        else:
            self.running_count -= 1
            if event == 'SUCCESS':
                color = self.green
            else:
                color = self.red
            self.show(self.format_event(event, name))
        self.flush()

    def update_status(self):
        self.clear_status()
        self.show_status()

    def clear_status(self):
        self.buffer += "\033[0E\033[K"

    def show_status(self):
        if self.running_count:
            self.buffer += '[%d tests running]' % (self.running_count,)

    def show(self, line):
        self.clear_status()
        self.buffer += line + "\n"
        self.show_status()

    def flush(self):
        sys.stdout.write(self.buffer)
        self.buffer = ''
        sys.stdout.flush()
        
class Locked():
    def __init__(self, value=None):
        self.value = value
        self.lock = Lock()

    def __enter__(self):
        self.lock.acquire()
        return self.value

    def __exit__(self, e, x, c):
        self.lock.release()
            
class TestProcess():
    def __init__(self, runner, id, test, dir):
        self.runner = runner
        self.id = id
        self.name = id[0]
        self.test = test
        self.timeout = test.timeout() or runner.timeout
        self.supervisor = None
        self.process = None
        self.dir = dir

    def start(self):
        self.runner.semaphore.acquire()
        try:
            self.runner.tell(TestRunner.STARTED, self.id)
            mkdir(self.dir)
            self.supervisor = Thread(target=self.supervise,
                                     name="supervisor:"+self.name)
            self.supervisor.daemon = True
            self.supervisor.start()
        except Exception:
            self.runner.semaphore.release()
            raise

    def run(self, write_pipe):
        sys.stdin.close()
        redirect_fd_to_file(1, join(self.dir, "stdout"), tee=self.runner.verbose)
        redirect_fd_to_file(2, join(self.dir, "stderr"), tee=self.runner.verbose)
        with Timeout(self.timeout):
            try:
                self.test.run()
            except TimeoutException:
                write_pipe.send(TestRunner.TIMED_OUT)
            except Exception:
                sys.stderr.write(traceback.format_exc() + '\n')
                write_pipe.send(TestRunner.FAILED)
            else:
                write_pipe.send(TestRunner.SUCCESS)

    def write_fail_message(self, message):
        with open(join(self.dir, "stderr"), 'a') as file:
            file.write(message)
                
    def supervise(self):
        try:
            read_pipe, write_pipe = Pipe(False)
            self.process = Process(target=self.run, args=[write_pipe],
                                   name="subprocess:"+self.name)
            self.process.start()
            self.process.join(self.timeout + 5)
            if self.process.is_alive():
                self.process.terminate()
                self.write_fail_message("Test failed to exit after timeout of %d seconds"
                                        % (self.timeout,))
                self.runner.tell(TestRunner.FAILED, self.id)
            elif self.process.exitcode:
                self.write_fail_message("Test exited abnormally with error code %d"
                                        % (self.process.exitcode,))
                self.runner.tell(TestRunner.FAILED, self.id)
            else:
                try:
                    write_pipe.close()
                    status = read_pipe.recv()
                except EOFError:
                    self.write_fail_message("Test did not fail, but"
                                            " failed to report its success")
                    status = TestRunner.FAILED
                self.runner.tell(status, self.id)
        finally:
            self.runner.semaphore.release()
                

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
    def __init__(self, timeout=None):
        self._timeout = timeout

    def run(self):
        raise Exception("run is not defined for the %s class" %
                        (type(self).__name__,))

    def filter(self, filter):
        if filter.match():
            return self
        else:
            return None

    def __iter__(self):
        yield (None, self)

    def timeout(self):
        return self._timeout

    def requirements(self):
        return []

    def configure(self, conf):
        return self

class SimpleTest(Test):
    def __init__(self, run, **kwargs):
        Test.__init__(self, **kwargs)
        self._run = run 

    def run(self):
        self._run()
        
class TestTree(Test):
    def __init__(self, tests={}):
        self.tests = dict(tests)

    def filter(self, filter):
        if filter.all_same():
            if filter.match():
                return self
            else:
                return TestTree()
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

    def requirements(self):
        for test in self.tests.values():
            for req in test.requirements():
                yield req        
                    
    def configure(self, conf):
        return TestTree((
            (name, test.configure(conf))
            for name, test
            in self.tests.iteritems()
        ))

    def __len__(self):
        count = 0
        for __, ___ in self:
            count += 1
        return count
