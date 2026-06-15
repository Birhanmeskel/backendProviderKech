from django.test import TestCase
from core.tasks import add

class AddTaskTestCase(TestCase):
    def test_add_with_positive_integers(self):
        result = add(2, 3)
        self.assertEqual(result, 5)

    def test_add_with_negative_integers(self):
        result = add(-4, -6)
        self.assertEqual(result, -10)

    def test_add_with_mixed_sign_integers(self):
        result = add(-7, 10)
        self.assertEqual(result, 3)
