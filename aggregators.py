import aiohttp
from pytoniq_core.boc.address import Address
import json

"""
Coffee.swap
To get route we run /v1/route endpoint. It returns us json which contains expected amount and paths.
Then to emulate, we pass path to v2/route/transactions endpoint and get the messages.
Then we need to build external message that sends these messages as internals and emulate through toncenter.

Example of /v1/route request:
curl --request POST \
  --url https://backend.swap.coffee/v1/route \
  --header 'Content-Type: application/json' \
  --data '{
  "input_token": {
    "blockchain": "ton",
    "address": "native"
  },
  "output_token": {
    "blockchain": "ton",
    "address": "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
  },
  "input_amount": 1,
  "max_splits": 4,
  "max_length": 3,
  "pool_selector": {
  }
}'

Response will contain:
{
   ....
  "output_amount": 3.4717588560243358,
  "paths": [...]
}

Example of /v2/route/transactions request:
curl --request POST \
  --url https://backend.swap.coffee/v2/route/transactions \
  --header 'Content-Type: application/json' \
  --data '{
  "sender_address": "UQBGFBa0OAHi9jT1kq8PNy1OXW4CfMJkPAl4wQsP2gNJWkpJ",
  "slippage": 1,
  "paths": [ ... ]
}'

Response will contain:
{
  "route_id": 1740239,
  "transactions": [
    {
      "address": "...",
      "value": "18162793568750000",
      "cell": "...",
      "send_mode": 3,
      "query_id": 6201176916867556
    },
    ...
  ]
}
"""

# we give it input token address, output token address, input amount, 
# and get output amount and messages for emulation
# we want to use async functions so we can ask multiple aggregators at the same time
async def get_coffe_swap_route(SENDER_ADDRESS, input_token, output_token, input_amount):
    if input_token == "ton":
        input_token = "native" # coffee uses "native" instead of ton
    if output_token == "ton":
        output_token = "native"
    # get route
    route_request = {
        "input_token": {
            "blockchain": "ton",
            "address": input_token
        },
        "output_token": {
            "blockchain": "ton",
            "address": output_token
        },
        "input_amount": input_amount,
        "max_splits": 4,
        "max_length": 3,
        "pool_selector": {
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post("https://backend.swap.coffee/v1/route", json=route_request) as response:
            route = await response.json()
            # get transactions
            transactions_request = {
                "sender_address": SENDER_ADDRESS,
                "slippage": 0.01,
                "paths": route["paths"]
            }
        async with session.post("https://backend.swap.coffee/v2/route/transactions", json=transactions_request) as response:
            transactions = await response.json()
            return route["output_amount"], transactions["transactions"]


async def get_dedust_route(SENDER_ADDRESS, input_token, output_token, input_amount, output_token_decimals):
    if input_token == "ton":
        input_token = "native" # dedust uses "native" instead of ton
    if output_token == "ton":
        output_token = "native"
    # get route
    quote_request = {
      "in_minter": input_token,
      "out_minter": output_token,
      "amount": input_amount,
      "swap_mode": "exact_in",
      "protocols": [], # with empty list it will be filled with default protocols (all)
      "only_verified_pools": True,
      "slippage_bps": 100,
      "max_splits": 4,
      "max_length": 3
    }

    async with aiohttp.ClientSession() as session:
        async with session.post("https://api-mainnet.dedust.io/v1/router/quote", json=quote_request) as response:
            quote = await response.json()

            swap_request = {
                "sender_address": SENDER_ADDRESS,
                "swap_data": {
                  "slippage_bps": 100,
                  "routes": quote["swap_data"]["routes"]
                }
            }
        async with session.post("https://api-mainnet.dedust.io/v1/router/swap", json=swap_request) as response:
            transactions = await response.json()
            ui_amount_out = int(quote["out_amount"]) / 10**output_token_decimals
            return ui_amount_out, transactions["transactions"]


# it is better to use 3rd-party service to get prices, but for now I found xdelta endpoint and will use it
async def get_prices():
    async with aiohttp.ClientSession() as session:
        prices_request = {}
        async with session.post("https://backend.xdelta.fi/api/v1/prices", json=prices_request) as response:
            prices = await response.json()
    # convert back
    prices = prices["data"]["prices"]
    result = {}
    for address in prices:
        r_address = address
        if address == "TON":
            r_address = "ton"
        else:
            r_address = Address(address).to_str(is_user_friendly=False).upper()
        result[r_address] = prices[address]
    return result
