import pytoniq_core
from pytoniq_core.tlb.transaction import ExternalMsgInfo, MessageAny, InternalMsgInfo, CurrencyCollection
from pytoniq_core.boc.address import Address
from pytoniq_core.tlb.custom.wallet import WalletMessage
import base64
import pytoniq
from pytoniq_core.boc import Cell
from pytoniq.contract.wallets import WalletV3, WalletV4

def build_payload(payload):
    # we expect that payload came in base64, so we need to convert it to bytes
    if not payload:
        return Cell.empty()
    return Cell.one_from_boc(payload)


def build_wallet_message(SENDER_ADDRESS, address, amount, payload, mode = 3):
    payload = build_payload(payload)
    info = InternalMsgInfo(
        ihr_disabled=True,
        bounce=True,
        bounced=False,
        src = Address(SENDER_ADDRESS),
        dest = Address(address),
        value = CurrencyCollection(amount),
        ihr_fee = 0,
        fwd_fee = 0,
        created_lt = 0,
        created_at = 0
    )
    message =  MessageAny(info=info, init=None, body=payload)
    return WalletMessage(send_mode = mode, message = message)

# we want to build external message that sends a list of internal messages
def raw_build_external_message(SENDER_ADDRESS, seqno, messages):
    external_message_body = WalletV4.raw_create_transfer_msg(
        private_key = b"\x07"*32, # we don't need private key, so we can put any
        seqno = seqno,
        wallet_id = 698983191, #default wallet id
        messages = messages
    )
    external = WalletV4.create_external_msg(dest = Address(SENDER_ADDRESS),
                                          body = external_message_body)
    return external


def build_external_message(SENDER_ADDRESS, seqno, messages):
    msgs = []
    for msg in messages:
        amount = msg.get("value")
        if not amount:
            amount = msg.get("amount", 0)
        amount = int(amount)
        payload = msg.get("payload")
        if not payload:
            payload = msg.get("cell")
        # payload can be empty
        msgs.append(build_wallet_message(SENDER_ADDRESS, msg["address"], amount, payload, msg.get("send_mode", 3)))
    return base64.b64encode(raw_build_external_message(SENDER_ADDRESS, seqno, msgs).serialize().to_boc())