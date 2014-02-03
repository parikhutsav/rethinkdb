from test.framework import RequireMakeTarget, TestTree

class UnitTests():
    def __init__(self, filters=[]):
        self.filters = filters
        self.configured = False
        self.tests = None

    def filter(self, filter):
        return UnitTests(self.filters + [filter])

    def check_configured(self):
        if not self.configured:
            raise Exception('Cannot run unit tests:'
                            ' rethinkdb-unittest executable not configured')

    def run(self):
        self.check_configured() 

    def __iter__(self):
        self.check_configured()

    def requirements():
        yield RequireMakeTarget('rethinkdb-unittest')
        
    def configure(self, conf):
        
