# Import necessary modules
import asyncio
import json
import ssl
import websockets
import requests
from google.protobuf.json_format import MessageToDict
import sys
import os
# sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'UPST')))
from UPFunctions import get_property
import MarketDataFeedV3_pb2 as pb
from Test import getOHLCVFromFeed, save_dict

i = 0

def get_market_data_feed_authorize_v3():
    """Get authorization for market data feed."""
    access_token = get_property('token')
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }
    url = 'https://api.upstox.com/v3/feed/market-data-feed/authorize'
    api_response = requests.get(url=url, headers=headers)
    return api_response.json()


def decode_protobuf(buffer):
    """Decode protobuf message."""
    feed_response = pb.FeedResponse()
    feed_response.ParseFromString(buffer)
    return feed_response


async def fetch_market_data():
    """Fetch market data using WebSocket and print it."""

    # Create default SSL context
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    # Get market data feed authorization
    response = get_market_data_feed_authorize_v3()
    # Connect to the WebSocket with SSL context
    async with websockets.connect(response["data"]["authorized_redirect_uri"], ssl=ssl_context) as websocket:
        print('Connection established')

        await asyncio.sleep(1)  # Wait for 1 second

        # Data to be sent over the WebSocket
        data = {
            "guid": "someguid",
            "method": "sub",
            "data": {
                "mode": "full",
                "instrumentKeys": ["NSE_EQ|INE062A01020"]
            }
        }

        # Convert data to binary and send over WebSocket
        binary_data = json.dumps(data).encode('utf-8')
        await websocket.send(binary_data)

        # Continuously receive and decode data from WebSocket
        counter = 0
        while True:
            message = await websocket.recv()
            decoded_data = decode_protobuf(message)

            # Convert the decoded data to a dictionary
            data_dict = MessageToDict(decoded_data)

            # Print the dictionary representation
            # data_json = json.dumps(data_dict, indent=4)
            # print(data_json)
            if counter == 0:
                counter += 1
                continue  # Skip the first iteration
            # print("New Tick:")
            dict = getOHLCVFromFeed(data_dict)
            save_dict(dict)
            print(json.dumps(dict))


# Execute the function to fetch market data
asyncio.run(fetch_market_data())
