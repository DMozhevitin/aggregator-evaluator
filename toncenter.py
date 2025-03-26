import aiohttp
'''
curl -X 'GET' \
  'https://toncenter.com/api/v3/walletStates?address=UQBGFBa0OAHi9jT1kq8PNy1OXW4CfMJkPAl4wQsP2gNJWkpJ' \
  -H 'accept: application/json'
'''
# load api key from environment
import os
from pytoniq_core.boc.address import Address
toncenter_api_key = os.getenv("TONCENTER_API_KEY")

async def get_wallet_seqno(address):
    # add api key to headers
    headers = { "accept": "application/json", "X-API-Key": toncenter_api_key }
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://toncenter.com/api/v3/walletStates?address={address}", headers = headers) as response:
            wallet = await response.json()
            return wallet["wallets"][0]["seqno"]

"""
 toncenter emulation works as follows:
 it accepts the following json
 {
  "boc": "te6ccgEBAQEAAgAAAA==",
  "ignore_chksig": true,
  "with_actions": true
}
and returns emulation result
"""

async def emulate(boc):
    async with aiohttp.ClientSession() as session:
        emulation_request = {
            "boc": boc.decode("utf-8"),
            "ignore_chksig": True,
            "include_code_data": False,
            "with_actions": True
        }
        headers = { "accept": "application/json", "X-API-Key": toncenter_api_key }
        async with session.post("https://toncenter.com/api/emulate/v1/emulateTrace", json=emulation_request, headers = headers) as response:
            emulation = await response.json()
            return emulation



"""
toncenter metadata api works as follows:
curl -X 'GET' \
  'https://toncenter.com/api/v3/metadata?address=0%3AB113A994B5024A16719F69139328EB759596C38A25F59028B146FECDC3621DFE' \
  -H 'accept: application/json'

  returns
{
  "0:B113A994B5024A16719F69139328EB759596C38A25F59028B146FECDC3621DFE": {
    "is_indexed": true,
    "token_info": [
      {
        "symbol": "USD₮",
        "extra": {
          "decimals": "9"
        }
      }
    ]
  }
}

we want to get token symbol for given address, but we also want to agrssively cache it via cache
"""

token_symbol_cache = {}

async def get_token_symbol(address):
    if address in token_symbol_cache:
        return token_symbol_cache[address]
    headers = { "accept": "application/json", "X-API-Key": toncenter_api_key }
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://toncenter.com/api/v3/metadata?address={address}", headers = headers) as response:
            metadata = await response.json()
            try:
              symbol = metadata[address]["token_info"][0]["symbol"]
            except:
                symbol = "UNKWN"
            token_symbol_cache[address] = symbol
            return symbol

token_decimals_cache = {}

async def get_token_decimals(address):
    if address == "ton":
        return 9
    # The keys of /api/v3/metadata response are raw addresses with uppercase letters,
    # so we convert the input address to have this format.
    address = Address(address).to_str(is_user_friendly=False).upper()
    if address in token_decimals_cache:
        return token_decimals_cache[address]
    headers = { "accept": "application/json", "X-API-Key": toncenter_api_key }
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://toncenter.com/api/v3/metadata?address={address}", headers = headers) as response:
            metadata = await response.json()
            try:
              decimals = int(metadata[address]["token_info"][0]["extra"]["decimals"])
            except:
                decimals = 9
            token_decimals_cache[address] = decimals
            return decimals
