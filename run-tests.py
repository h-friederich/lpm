#!/usr/bin/env python
import sys
import os
import unittest

pattern = 'test*.py'
if len(sys.argv) > 1:
    pattern = sys.argv[1]

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
suite = unittest.TestLoader().discover('', pattern=pattern)
unittest.TextTestRunner(verbosity=2).run(suite)