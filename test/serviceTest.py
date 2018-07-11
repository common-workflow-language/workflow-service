from __future__ import absolute_import
import unittest


class ServiceTest(unittest.TestCase):
    """A set of test cases for x.py"""
    def setUp(self):
        """Setup variables."""
        self.var = 'a'

    def tearDown(self):
        """Default tearDown for unittest."""
        unittest.TestCase.tearDown(self)

    def test_1(self):
        self.assertEqual(1, 1)


if __name__ == "__main__":
    unittest.main()  # run all tests
