import unittest
from unittest.mock import patch

from bubbot.frame_data import frame_output


class _SentMessage:
    id = 123


class _FakeChannel:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.calls = []

    async def send(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail:
            raise RuntimeError("channel send failed")
        return _SentMessage()


class _FakeMessage:
    def __init__(self, *, fail_reply=False, fail_files=False):
        self.author = type("Author", (), {"id": 1})()
        self.content = "terry 2hk"
        self.channel = _FakeChannel()
        self.fail_reply = fail_reply
        self.fail_files = fail_files
        self.reply_calls = []

    async def reply(self, **kwargs):
        self.reply_calls.append(kwargs)
        if self.fail_reply or (self.fail_files and kwargs.get("files")):
            raise RuntimeError("reply send failed")
        return _SentMessage()


class _FakeView:
    def __init__(self, embed):
        self.embed = embed

    def build_embed(self):
        return self.embed

    def initial_files(self):
        return [object()]


class _FakeInteractionResponse:
    def __init__(self):
        self.defer_calls = 0

    async def defer(self):
        self.defer_calls += 1


class _FakeInteraction:
    def __init__(self, attachments):
        self.response = _FakeInteractionResponse()
        self.message = type("Message", (), {"attachments": attachments})()
        self.edit_calls = []

    async def edit_original_response(self, **kwargs):
        self.edit_calls.append(kwargs)


class _LinkMessage:
    def __init__(self):
        self.replies = []

    async def reply(self, content):
        self.replies.append(content)
        return _SentMessage()


class FrameEmbedOutputTests(unittest.IsolatedAsyncioTestCase):
    async def test_remote_gif_url_is_preferred_over_local_backup(self):
        message = _LinkMessage()

        with patch("bubbot.frame_data.frame_output.get_existing_local_gif_asset_paths") as local_lookup:
            sent_ids = await frame_output.send_gif_links_response(
                message,
                ["/local/backup.gif", "https://ultimateframedata.com/sf6/hitboxes/alex/alex-prowler-hp.gif"],
            )

        self.assertEqual([123], sent_ids)
        self.assertEqual(
            ["https://ultimateframedata.com/sf6/hitboxes/alex/alex-prowler-hp.gif"],
            message.replies,
        )
        local_lookup.assert_not_called()

    async def test_panel_toggle_defers_and_reuses_existing_attachments(self):
        existing_attachment = object()
        interaction = _FakeInteraction([existing_attachment])
        view = _FakeView(object())

        await frame_output._edit_frame_data_view(interaction, view, [object()])

        self.assertEqual(1, interaction.response.defer_calls)
        self.assertEqual([existing_attachment], interaction.edit_calls[0]["attachments"])

    async def test_panel_toggle_can_remove_existing_attachments(self):
        interaction = _FakeInteraction([object()])
        view = _FakeView(object())

        await frame_output._edit_frame_data_view(interaction, view, [])

        self.assertEqual(1, interaction.response.defer_calls)
        self.assertEqual([], interaction.edit_calls[0]["attachments"])

    async def test_attachment_failure_retries_as_embed_without_plain_text(self):
        embed = object()
        message = _FakeMessage(fail_files=True)
        view = _FakeView(embed)

        with (
            patch("bubbot.features.menu_system.build_frame_result_view", return_value=view),
            patch("bubbot.features.failed_prompt_report.stamp_report_context_on_sent"),
        ):
            sent_ids = await frame_output.send_frame_table_response(
                message,
                [{"char_name": "terry", "moveName": "Crouch HK", "numCmd": "2HK"}],
                "plain text must never be sent",
            )

        self.assertEqual([123], sent_ids)
        self.assertEqual(2, len(message.reply_calls))
        self.assertTrue(all(call.get("embed") is embed for call in message.reply_calls))
        self.assertTrue(all("content" not in call for call in message.reply_calls))
        self.assertIn("files", message.reply_calls[0])
        self.assertNotIn("files", message.reply_calls[1])

    async def test_reply_failure_retries_as_channel_embed(self):
        embed = object()
        view = object()
        message = _FakeMessage(fail_reply=True)

        sent = await frame_output._send_frame_embed_only(
            message,
            embed,
            view=view,
            files=[object()],
            reply=True,
        )

        self.assertEqual(123, sent.id)
        self.assertTrue(message.channel.calls)
        self.assertTrue(all(call.get("embed") is embed for call in message.reply_calls))
        self.assertTrue(all("content" not in call for call in message.reply_calls))
        self.assertTrue(all(call.get("embed") is embed for call in message.channel.calls))
        self.assertTrue(all("content" not in call for call in message.channel.calls))


if __name__ == "__main__":
    unittest.main()
