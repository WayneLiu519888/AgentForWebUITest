from src.reporter import TestReporter
r = TestReporter('reports')
methods = [m for m in dir(r) if not m.startswith('_')]
print('All methods:', methods)
print('Total public methods:', len(methods))
