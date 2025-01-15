import pytest
from unittest.mock import AsyncMock, patch
from otomai.services.notifier import TelegramNotifier


@pytest.fixture
def mock_bot():
    """Fixture to mock the telegram.Bot instance."""
    with patch("otomai.services.notifier.telegram.Bot", autospec=True) as mock:
        yield mock


@pytest.fixture
def valid_telegram_notifier(mock_bot):
    """Fixture to provide a valid instance of TelegramNotifier with a mocked bot."""
    mock_bot_instance = mock_bot.return_value
    mock_bot_instance.send_message = AsyncMock()
    mock_bot_instance.send_photo = AsyncMock()

    return TelegramNotifier(
        chat_id="test_chat_id",
        bot=mock_bot_instance,
    )


@pytest.mark.asyncio
async def test_send_message(valid_telegram_notifier):
    """Test the send_message method of TelegramNotifier."""
    await valid_telegram_notifier.send_message("Test message")
    valid_telegram_notifier.bot.send_message.assert_called_once_with(
        chat_id="test_chat_id", text="Test message"
    )


@pytest.mark.asyncio
async def test_send_image(valid_telegram_notifier):
    """Test the send_image method of TelegramNotifier."""
    await valid_telegram_notifier.send_image("test_image.jpg", "Test caption")
    valid_telegram_notifier.bot.send_photo.assert_called_once_with(
        chat_id="test_chat_id", photo="test_image.jpg", caption="Test caption"
    )


def test_notifier_kind(valid_telegram_notifier):
    """Test that the KIND attribute is correctly set."""
    assert valid_telegram_notifier.KIND == "Telegram"
