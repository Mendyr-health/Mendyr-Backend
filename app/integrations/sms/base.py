from typing import Protocol


class SMSProvider(Protocol):
    async def send_otp(self, phone_number: str, code: str) -> None: ...

    async def send_message(self, phone_number: str, message: str) -> None: ...
