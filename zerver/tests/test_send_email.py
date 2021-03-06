import smtplib
from unittest import mock

from django.core.mail.backends.locmem import EmailBackend
from django.core.mail.backends.smtp import EmailBackend as SMTPBackend
from django.core.mail.message import sanitize_address

from zerver.lib.send_email import FromAddress, build_email, initialize_connection
from zerver.lib.test_classes import ZulipTestCase

OVERLY_LONG_NAME = "Z̷̧̙̯͙̠͇̰̲̞̙͆́͐̅̌͐̔͑̚u̷̼͎̹̻̻̣̞͈̙͛͑̽̉̾̀̅̌͜͠͞ļ̛̫̻̫̰̪̩̠̣̼̏̅́͌̊͞į̴̛̛̩̜̜͕̘̂̑̀̈p̡̛͈͖͓̟͍̿͒̍̽͐͆͂̀ͅ A̰͉̹̅̽̑̕͜͟͡c̷͚̙̘̦̞̫̭͗̋͋̾̑͆̒͟͞c̵̗̹̣̲͚̳̳̮͋̈́̾̉̂͝ͅo̠̣̻̭̰͐́͛̄̂̿̏͊u̴̱̜̯̭̞̠͋͛͐̍̄n̸̡̘̦͕͓̬͌̂̎͊͐̎͌̕ť̮͎̯͎̣̙̺͚̱̌̀́̔͢͝ S͇̯̯̙̳̝͆̊̀͒͛̕ę̛̘̬̺͎͎́̔̊̀͂̓̆̕͢ͅc̨͎̼̯̩̽͒̀̏̄̌̚u̷͉̗͕̼̮͎̬͓͋̃̀͂̈̂̈͊͛ř̶̡͔̺̱̹͓̺́̃̑̉͡͞ͅi̶̺̭͈̬̞̓̒̃͆̅̿̀̄́t͔̹̪͔̥̣̙̍̍̍̉̑̏͑́̌ͅŷ̧̗͈͚̥̗͚͊͑̀͢͜͡"


class TestBuildEmail(ZulipTestCase):
    def test_build_SES_compatible_From_field(self) -> None:
        hamlet = self.example_user("hamlet")
        from_name = FromAddress.security_email_from_name(language="en")
        mail = build_email(
            "zerver/emails/password_reset",
            to_emails=[hamlet],
            from_name=from_name,
            from_address=FromAddress.NOREPLY,
            language="en",
        )
        self.assertEqual(
            mail.extra_headers["From"], "{} <{}>".format(from_name, FromAddress.NOREPLY)
        )

    def test_build_SES_compatible_From_field_limit(self) -> None:
        hamlet = self.example_user("hamlet")
        limit_length_name = "a" * (320 - len(sanitize_address(FromAddress.NOREPLY, "utf-8")) - 3)
        mail = build_email(
            "zerver/emails/password_reset",
            to_emails=[hamlet],
            from_name=limit_length_name,
            from_address=FromAddress.NOREPLY,
            language="en",
        )
        self.assertEqual(
            mail.extra_headers["From"], "{} <{}>".format(limit_length_name, FromAddress.NOREPLY)
        )

    def test_build_SES_incompatible_From_field(self) -> None:
        hamlet = self.example_user("hamlet")
        mail = build_email(
            "zerver/emails/password_reset",
            to_emails=[hamlet],
            from_name=OVERLY_LONG_NAME,
            from_address=FromAddress.NOREPLY,
            language="en",
        )
        self.assertEqual(mail.extra_headers["From"], FromAddress.NOREPLY)

    def test_build_SES_incompatible_From_field_limit(self) -> None:
        hamlet = self.example_user("hamlet")
        limit_length_name = "a" * (321 - len(sanitize_address(FromAddress.NOREPLY, "utf-8")) - 3)
        mail = build_email(
            "zerver/emails/password_reset",
            to_emails=[hamlet],
            from_name=limit_length_name,
            from_address=FromAddress.NOREPLY,
            language="en",
        )
        self.assertEqual(mail.extra_headers["From"], FromAddress.NOREPLY)


class TestSendEmail(ZulipTestCase):
    def test_initialize_connection(self) -> None:
        # Test the new connection case
        with mock.patch.object(EmailBackend, "open", return_value=True):
            backend = initialize_connection(None)
            self.assertTrue(isinstance(backend, EmailBackend))

        backend = mock.MagicMock(spec=SMTPBackend)
        backend.connection = mock.MagicMock(spec=smtplib.SMTP)

        self.assertTrue(isinstance(backend, SMTPBackend))

        # Test the old connection case when it is still open
        backend.open.return_value = False
        backend.connection.noop.return_value = [250]
        initialize_connection(backend)
        self.assertEqual(backend.open.call_count, 1)
        self.assertEqual(backend.connection.noop.call_count, 1)

        # Test the old connection case when it was closed by the server
        backend.connection.noop.return_value = [404]
        backend.close.return_value = False
        initialize_connection(backend)
        # 2 more calls to open, 1 more call to noop and 1 call to close
        self.assertEqual(backend.open.call_count, 3)
        self.assertEqual(backend.connection.noop.call_count, 2)
        self.assertEqual(backend.close.call_count, 1)

        # Test backoff procedure
        backend.open.side_effect = OSError
        with self.assertRaises(OSError):
            initialize_connection(backend)
        # 3 more calls to open as we try 3 times before giving up
        self.assertEqual(backend.open.call_count, 6)
