from test import Test

def main(args):

    if args.empty():
        tests = Tests([Tests.from_name(test) for test in args])
    else:
        tests = Tests.from_name("default")

    tests.run()
