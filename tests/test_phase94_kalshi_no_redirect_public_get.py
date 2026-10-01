import unittest
from unittest.mock import MagicMock, patch
from urllib.request import Request

from signal_vault.forward_capture import _RejectRedirects
from signal_vault.kalshi_public_research import (
    MAX_RESPONSE_BYTES,
    _default_transport,
)


class KalshiNoRedirectTransportTests(unittest.TestCase):
    def test_default_transport_uses_redirect_rejecting_opener(self):
        request=Request(
            "https://external-api.kalshi.com/trade-api/v2/markets",
            method="GET",
        )
        response=MagicMock()
        response.read.return_value=b'{"markets":[],"cursor":""}'
        context=MagicMock()
        context.__enter__.return_value=response
        context.__exit__.return_value=False
        opener=MagicMock()
        opener.open.return_value=context

        with patch(
            "signal_vault.kalshi_public_research.build_opener",
            return_value=opener,
        ) as build:
            raw=_default_transport(request,15.0)

        build.assert_called_once_with(_RejectRedirects)
        opener.open.assert_called_once_with(request,timeout=15.0)
        response.read.assert_called_once_with(MAX_RESPONSE_BYTES+1)
        self.assertEqual(raw,b'{"markets":[],"cursor":""}')

    def test_redirect_handler_explicitly_refuses_redirect_request(self):
        handler=_RejectRedirects()
        with self.assertRaises(ValueError):
            handler.redirect_request(
                Request("https://external-api.kalshi.com/trade-api/v2/markets"),
                None,
                302,
                "Found",
                {},
                "https://example.com/redirected",
            )


if __name__=="__main__":
    unittest.main()
