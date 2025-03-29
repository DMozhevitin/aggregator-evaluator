"""
There are multiple DEX aggregators on TON. That means that for given swap (X amount of asset A to B)
it returns "routes" (a few chains of swaps A->C->D->B) that are the most profitable (as these aggregator believes)
and final output amount of asset B.

We are interested in 2 things:
first which aggregator returns the most profitable route in accordance to their own evaluation
and second which returns the most profitable route in reality. Since it is too expensive to check
result in reality we will check it with tonapi emulation.

"""



import aiohttp
import json
import time
SENDER_ADDRESS = "UQAPPgN25OQh3EOqqt0v_CRmScxa-_ulVwm5NESN1DO4gZzD" # Kiba.ton, a lot of TON and USDT

from aggregators import get_coffe_swap_route, get_dedust_route, get_prices
from toncenter import get_wallet_seqno, emulate, get_token_symbol, get_token_decimals, get_mc_seq_no
from messages import build_external_message
from pytoniq_core.boc.address import Address
from functools import partial


async def assess_emulation(emulation, sender_address, input_token, input_amount, output_token, prices, aggregator):
    """
    emulation return the following json:
    {
        "transactions": {"hash": {"account_state_hash_before":X, "account_state_hash_after":Y }},
        "account_states" : {"hash": {"balance": X, "last_trans_lt":Y}}
        "trace": { "tx_hash": X, "children": [ {"tx_hash": Y, "children":[...]} ] },
        "actions": [{}, ...]
    }
    """
    # first we want to get the first and last transaction on sender address
    # lets build account->lt->state map
    accounts = {}
    if not "transactions" in emulation:
        print("Error: no transactions in emulation", emulation)
    for tx_hash in emulation["transactions"]:
        transaction = emulation["transactions"][tx_hash]
        account_address = transaction["account"]
        if not account_address in accounts:
            accounts[account_address] = {}
        prev_state = transaction["account_state_before"]
        after_state = transaction["account_state_after"]
        lt = int(transaction["lt"])
        if not lt in accounts[account_address]:
            accounts[account_address][lt] = prev_state
        if not lt in accounts[account_address]:
            accounts[account_address][lt] = after_state
    # we want to know initial and final balance on sender_address
    # problem that sender_address is in friendly format and emulation is in raw format
    raw_sender_address = Address(sender_address).to_str(is_user_friendly=False).upper()
    sender_account = accounts[raw_sender_address]

    initial_balance = int(sender_account[min(sender_account.keys())]["balance"])
    final_balance = int(sender_account[max(sender_account.keys())]["balance"])
    ton_amount_diff = final_balance - initial_balance
    # now we want to get how much jetton we sent and received
    # emulation returns actions, here we are interested in jetton_swap and jetton_transfer(for not yet parsable swaps)
    """
    Example of the jetton_swap:
            {
            "success": true,
            "type": "jetton_swap",
            "details": {
                "dex": "stonfi_v2",
                "sender": "0:0F3E0376E4E421DC43AAAADD2FFC246649CC5AFBFBA55709B934448DD433B881",
                "dex_incoming_transfer": {
                    "asset": null,
                    "source": "0:0F3E0376E4E421DC43AAAADD2FFC246649CC5AFBFBA55709B934448DD433B881",
                    "destination": "0:92E1411AE546892F33B2C8A89EA90390D8FF4CFBB917A643B91E73F706FDB9D1",
                    "source_jetton_wallet": null,
                    "destination_jetton_wallet": "0:9220C181A6CFEACD11B7B8F62138DF1BB9CC82B6ED2661D2F5FAEE204B3EFB20",
                    "amount": "5298486708268"
                },
                "dex_outgoing_transfer": {
                    "asset": "0:B113A994B5024A16719F69139328EB759596C38A25F59028B146FECDC3621DFE",
                    "source": "0:92E1411AE546892F33B2C8A89EA90390D8FF4CFBB917A643B91E73F706FDB9D1",
                    "destination": "0:3D264E3CB401B01DC7D1CFC232470D185A3EBA63D933E738617F9942B9294C4E",
                    "source_jetton_wallet": "0:922D627D7D8EDBD00E4E23BDB0C54A76EE5E1F46573A1AF4417857FA3E23E91F",
                    "destination_jetton_wallet": "0:27DC8F74439515FB5A7C27651E53BBE3F1EBE2900504CC38845E2065A5F5DB83",
                    "amount": "18835347502"
                },
                "peer_swaps": []
            }
        }
    """
    # a few notes, if asset OR source_jetton_wallet OR destination_jetton_wallet are null, it means that it is TON (just proxied as jetton)
    # if asset is not null, it is jetton

    #lets calc what we send (that means sum of amounts in dex_incoming_transfer where source is sender_address) and jetton_transfer
    # and what we received (that means sum of amounts in dex_outgoing_transfer where destination is sender_address) and jetton_transfer
    def is_pton(dex_transfer):
        return (dex_transfer["source_jetton_wallet"] == None) or (dex_transfer["destination_jetton_wallet"] == None)

    short_descriptions_out = []
    short_descriptions_in  = []
    sent_amounts = {}
    received_amounts = {}
    for action in emulation["actions"]:
        if action["type"] == "jetton_swap":
            if action["details"]["dex_incoming_transfer"]["source"] == raw_sender_address:
                asset = action["details"]["dex_incoming_transfer"]["asset"]
                other_asset = action["details"]["dex_outgoing_transfer"]["asset"]
                if is_pton(action["details"]["dex_incoming_transfer"]):
                    asset = "ton"
                if not asset in sent_amounts:
                    sent_amounts[asset] = 0
                sent_amounts[asset] += int(action["details"]["dex_incoming_transfer"]["amount"])
                short_descriptions_out.append(
                    { "DEX": action['details']['dex'],
                      "IN": action['details']['dex_incoming_transfer']['amount'],
                      "IN_ASSET": action['details']['dex_incoming_transfer']['asset'],
                      "IN_ASSET_SHORT": await get_token_symbol(action['details']['dex_incoming_transfer']['asset']),
                      "OUT": action['details']['dex_outgoing_transfer']['amount'],
                      "OUT_ASSET": action['details']['dex_outgoing_transfer']['asset'],
                      "OUT_ASSET_SHORT": await get_token_symbol(action['details']['dex_outgoing_transfer']['asset'])
                     })
                #f"Swap {action['details']['dex']} {float(action['details']['dex_incoming_transfer']['amount'])/ (10 ** (await get_token_decimals(asset)))} {await get_token_symbol(asset)} -> {float(action['details']['dex_outgoing_transfer']['amount'])/ (10 ** (await get_token_decimals(other_asset)))} {await get_token_symbol(other_asset)}")
            if action["details"]["dex_outgoing_transfer"]["destination"] == raw_sender_address:
                asset = action["details"]["dex_outgoing_transfer"]["asset"]
                other_asset = action["details"]["dex_incoming_transfer"]["asset"]
                if is_pton(action["details"]["dex_outgoing_transfer"]):
                    asset = "ton"
                if not asset in received_amounts:
                    received_amounts[asset] = 0
                received_amounts[asset] += int(action["details"]["dex_outgoing_transfer"]["amount"])
                short_descriptions_in.append(
                    { "DEX": action['details']['dex'],
                      "IN": action['details']['dex_incoming_transfer']['amount'],
                      "IN_ASSET": action['details']['dex_incoming_transfer']['asset'],
                      "IN_ASSET_SHORT": await get_token_symbol(action['details']['dex_incoming_transfer']['asset']),
                      "OUT": action['details']['dex_outgoing_transfer']['amount'],
                      "OUT_ASSET": action['details']['dex_outgoing_transfer']['asset'],
                      "OUT_ASSET_SHORT": await get_token_symbol(action['details']['dex_outgoing_transfer']['asset'])
                     })
                #f"Swap {action['details']['dex']} {float(action['details']['dex_incoming_transfer']['amount'])/ (10 ** (await get_token_decimals(asset)))} {await get_token_symbol(asset)} -> {float(action['details']['dex_outgoing_transfer']['amount'])/ (10 ** (await get_token_decimals(other_asset)))} {await get_token_symbol(other_asset)}")
        if action["type"] == "jetton_transfer":
            if action["details"]["sender"] == raw_sender_address:
                asset = action["details"]["asset"]
                if not asset in sent_amounts:
                    sent_amounts[asset] = 0
                sent_amounts[asset] += int(action["details"]["amount"])
                short_descriptions_out.append(
                    {
                        "DEX": "UNKNOWN",
                        "IN": action['details']['amount'],
                        "IN_ASSET": action['details']['asset'],
                        "IN_ASSET_SHORT": await get_token_symbol(action['details']['asset'])
                    }
                )
                #short_descriptions_out.append(f"Transfer {float(action['details']['amount'])/ (10 ** (await get_token_decimals(asset)))} {await get_token_symbol(asset)}")
            if action["details"]["receiver"] == raw_sender_address:
                asset = action["details"]["asset"]
                if not asset in received_amounts:
                    received_amounts[asset] = 0
                received_amounts[asset] += int(action["details"]["amount"])
                short_descriptions_in.append(
                    {
                        "DEX": "UNKNOWN",
                        "OUT": action['details']['amount'],
                        "OUT_ASSET": action['details']['asset'],
                        "OUT_ASSET_SHORT": await get_token_symbol(action['details']['asset'])
                    }
                )
                #short_descriptions_in.append(f"Transfer {float(action['details']['amount'])/ (10 ** (await get_token_decimals(asset)))} {await get_token_symbol(asset)}")
    # lets print results
    #print("Ton diff:", ton_amount_diff,
    #      "Sent:", json.dumps(sent_amounts, indent=4),
    #      "Received:", json.dumps(received_amounts, indent=4))

    # lets also count total number of transactions
    count = 0
    max_depth = 0
    def add_children(tx, depth):
        nonlocal count, max_depth
        max_depth = max(max_depth, depth)
        count += 1
        for child in tx.get("children", []):
            add_children(child, depth + 1)
    for tx in [emulation["trace"]]:
        add_children(tx, 0)
    # not lets make hashmap in_msg -> tx_hash
    in_msg_to_tx = {}
    for tx in emulation["transactions"]:
        in_msg = emulation["transactions"][tx]["in_msg"]
        in_msg_to_tx[in_msg["hash"]] = tx
    # lets check if all messages from out_msg has corresponding in_msg
    for tx in emulation["transactions"]:
        for out_msg in emulation["transactions"][tx]["out_msgs"]:
            if not out_msg["hash"] in in_msg_to_tx:
                #print("Error: out_msg without in_msg", out_msg)
                pass
    #print("Trace_id:", emulation["trace"]["tx_hash"])
    #print("Total transactions:", count, max_depth)

    # Now we want to calculate "price": ratio of what we received to what we sent
    # we only want to take into account target received jetton, sent jetton and TON
    # we don't want to take into account any intermediate jettons

    #rewrite sent_amounts of ton to ton_amount_diff it is more correct since take into account gas fees
    sent_amounts["ton"] = -ton_amount_diff
    gas_fee = -ton_amount_diff # Gas fees is essentially the difference in TON balance
    # If input_asset == TON, we exclude its amount from gas fees
    if input_token == "ton":
        # swap.coffee and DeDust handles input_amount differently in terms of decimals, and
        # we should take it into account here
        gas_fee -= input_amount * (1 if aggregator == "dedust" else 10**9)
    # lets calculate USD value of what we sent and received
    sent_usd = 0
    received_usd = 0
    for asset in sent_amounts:
        sent_usd += sent_amounts[asset] * prices[asset]

    #for asset in received_amounts:
    #    received_usd += received_amounts[asset] * prices[asset]
    # only take into account target asset
    raw_output_token = Address(output_token).to_str(is_user_friendly=False).upper()
    received_usd = received_amounts.get(raw_output_token, 0) * prices[raw_output_token]

    # lets calculate the loss ratio
    if sent_usd == 0:
        return 0
    print(short_descriptions_out)
    real_out_amount = received_amounts.get(raw_output_token, 0)
    return received_usd / sent_usd, short_descriptions_out, short_descriptions_in, real_out_amount, gas_fee / 10**9








# lets put it all together
async def emulate_and_assess(mc_seq_no, seqno, get_route, input_token, output_token, input_amount, prices, aggregator):
    route = await get_route(SENDER_ADDRESS, input_token, output_token, input_amount)
    swap_external = build_external_message(SENDER_ADDRESS, seqno, route[1])
    swap_emulation = await emulate(mc_seq_no, swap_external)
    emulation_assesment, out_desc, in_descr, real_out_amount, gas_fees = await assess_emulation(swap_emulation, SENDER_ADDRESS, input_token, input_amount, output_token, prices, aggregator)
    return route[0], emulation_assesment, out_desc, in_descr, real_out_amount, gas_fees

async def emulate_and_assess_all(input_token, output_token, input_amount):
    seqno = await get_wallet_seqno(SENDER_ADDRESS)
    tasks = []
    in_decimals = await get_token_decimals(input_token)
    out_decimals = await get_token_decimals(output_token)

    prices = await get_prices()
    mc_seq_no = await get_mc_seq_no()
    tasks.append(emulate_and_assess(mc_seq_no, seqno, get_coffe_swap_route, input_token, output_token, input_amount, prices, "swap.coffee"))
    # Fix 'output_token_decimals' argument
    dedust_route_getter = partial(get_dedust_route, output_token_decimals=out_decimals)
    tasks.append(emulate_and_assess(mc_seq_no, seqno, dedust_route_getter, input_token, output_token, input_amount * 10**in_decimals, prices, "dedust"))
    results = await asyncio.gather(*tasks)

    real_output_swap_coffee = results[0][4]
    real_output_dedust = results[1][4]
    gas_fees_swap_coffee = results[0][5]
    gas_fees_dedust = results[1][5]
    print("Expected Coffee.swap:", results[0][0], "DeDust:", results[1][0])
    print("Real     Coffee.swap:", real_output_swap_coffee, "DeDust:", real_output_dedust)
    print("Loss R   Coffee.swap:", results[0][1], "DeDust:", results[1][1])
    print("Gas fees   Coffee.swap:", gas_fees_swap_coffee, "DeDust:", gas_fees_dedust)
    utime = int(time.time())
    insert_data(utime, "Coffee.swap", f"{input_amount} {input_token}->{output_token}", real_output_swap_coffee, results[0][1], results[0][2], results[0][3], gas_fees_swap_coffee)
    insert_data(utime, "DeDust", f"{input_amount} {input_token}->{output_token}", real_output_dedust, results[1][1], results[1][2], results[1][3], gas_fees_dedust)

    # Toncenter API key that is used doesn't support that much requests per seconds, so we wait a bit here
    await asyncio.sleep(1)

import asyncio

# Now we want to get SQLITE database where store data
# utime, aggregator, swap_type(what to what and amount), real_output, loss_ratio, short_descriptions_out, gas_fees
# then we want to  retrieve data for prev 24 hours (so index for utime) and given swap_type

def create_database_if_not_exists():
    import sqlite3
    conn = sqlite3.connect('aggregator.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS swaps
                 (utime INTEGER, aggregator TEXT, swap_type TEXT, real_output REAL, loss_ratio REAL, short_descriptions_out TEXT, short_descriptions_in TEXT, gas_fees REAL)''')
    # create indexes
    c.execute('''CREATE INDEX IF NOT EXISTS idx_utime ON swaps (utime)''')
    c.execute('''CREATE INDEX IF NOT EXISTS idx_swap_type ON swaps (swap_type)''')
    conn.commit()
    conn.close()

def insert_data(utime, aggregator, swap_type, real_output, loss_ratio, short_descriptions_out, short_descriptions_in, gas_fees):
    import sqlite3
    conn = sqlite3.connect('aggregator.db')
    c = conn.cursor()
    c.execute("INSERT INTO swaps VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (utime, aggregator, swap_type, real_output, loss_ratio, json.dumps(short_descriptions_out), json.dumps(short_descriptions_in), gas_fees))
    # also let's automatically remove more than week old data
    c.execute("DELETE FROM swaps WHERE utime < ?", (utime - 7 * 24 * 3600,))
    conn.commit()
    conn.close()


async def main():
    create_database_if_not_exists()
    USDT = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"
    ton = "ton"
    RAFF = "EQCJbp0kBpPwPoBG-U5C-cWfP_jnksvotGfArPF50Q9Qiv9h"
    delay = 5
    while True:
        await emulate_and_assess_all(ton, USDT, 1)
        await asyncio.sleep(delay)
        await emulate_and_assess_all(ton, USDT, 100)
        await asyncio.sleep(delay)
        await emulate_and_assess_all(ton, USDT, 10000)
        await asyncio.sleep(delay)

        await emulate_and_assess_all(ton, RAFF, 1)
        await asyncio.sleep(delay)
        await emulate_and_assess_all(ton, RAFF, 100)
        await asyncio.sleep(delay)
        await emulate_and_assess_all(ton, RAFF, 10000)
        await asyncio.sleep(delay)

        await emulate_and_assess_all(USDT, RAFF, 1)
        await asyncio.sleep(delay)
        await emulate_and_assess_all(USDT, RAFF, 100)
        await asyncio.sleep(delay)
        await emulate_and_assess_all(USDT, RAFF, 10000)
        await asyncio.sleep(delay)


if __name__ == '__main__':
    asyncio.run(main())
