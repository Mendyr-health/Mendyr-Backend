from app.core.config import settings
from app.integrations.sms.base import SMSProvider
from app.integrations.sms.console import ConsoleSMSProvider
from app.integrations.sms.msg91 import MSG91SMSProvider


def get_sms_provider() -> SMSProvider:
    if settings.SMS_PROVIDER == "msg91":
        return MSG91SMSProvider()
    return ConsoleSMSProvider()
