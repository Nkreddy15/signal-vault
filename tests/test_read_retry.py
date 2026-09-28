import io
import unittest
from urllib.error import HTTPError, URLError

from signal_vault.read_retry import ReadRetryPolicy, is_retryable_read_error, retry_read


class ReadRetryTests(unittest.TestCase):
    def http(self, code):
        return HTTPError("https://fixed.example", code, "x", {}, io.BytesIO())

    def test_transient_get_errors_retry_with_bounded_backoff(self):
        calls=[]; sleeps=[]
        def op():
            calls.append(1)
            if len(calls) < 3:
                raise URLError("temporary")
            return "ok"
        result=retry_read(op, policy=ReadRetryPolicy(attempts=3, initial_delay_seconds=.1,
                                                     max_delay_seconds=.2), sleeper=sleeps.append)
        self.assertEqual(result, "ok")
        self.assertEqual(sleeps, [.1, .2])

    def test_nontransient_4xx_and_parse_errors_never_retry(self):
        for exc in (self.http(401), ValueError("bad schema")):
            calls=[]
            def op(exc=exc):
                calls.append(1); raise exc
            with self.assertRaises(type(exc)):
                retry_read(op, sleeper=lambda _: self.fail("must not sleep"))
            self.assertEqual(len(calls), 1)

    def test_429_and_5xx_retryable_but_404_not(self):
        self.assertTrue(is_retryable_read_error(self.http(429)))
        self.assertTrue(is_retryable_read_error(self.http(503)))
        self.assertFalse(is_retryable_read_error(self.http(404)))

    def test_retry_limit_is_enforced(self):
        calls=[]
        def op():
            calls.append(1); raise TimeoutError()
        with self.assertRaises(TimeoutError):
            retry_read(op, policy=ReadRetryPolicy(attempts=2, initial_delay_seconds=0,
                                                   max_delay_seconds=0), sleeper=lambda _: None)
        self.assertEqual(len(calls), 2)
