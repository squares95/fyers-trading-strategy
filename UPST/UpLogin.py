from lib2to3.fixes.fix_renames import LOOKUP
import webbrowser
import urllib.parse
from flask import Flask, request
import threading
import requests
import time,os
import csv
from datetime import datetime


os.system('cls')
from UPFunctions import get_property,upsert_property, lookupKeys
import upstox_client
from upstox_client.rest import ApiException

app = Flask(__name__)
auth_code_value = None

key = get_property('key')
secret = get_property('secret')
redirectURL = get_property('redirectURL')
auth_code = get_property('auth_code')
grant_type = 'authorization_code'

def startBrowserForUPAuthCode():
    baseURL = "https://api.upstox.com/v2/login/authorization/dialog"
    params = {
    'client_id': key,
    'redirect_uri': redirectURL,
    'response_type' : 'code'
}
    query_string = urllib.parse.urlencode(params)
    full_url = f"{baseURL}?{query_string}"

    # print(full_url)
    webbrowser.open(full_url)

@app.route('/')
def capture_code():
    global auth_code_value
    auth_code_value = request.args.get('code')
    upsert_property('auth_code', auth_code_value)
    # print(f"✅ Captured auth_code: {auth_code_value}")
    return "You can close this tab now."


def run_flask():
    app.run(port=5000)

def get_auth_code():
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Give the server a moment to start
    time.sleep(1)

    startBrowserForUPAuthCode()

    # Wait for the auth_code to be captured
    while auth_code_value is None:
        time.sleep(0.5)

    upsert_property('auth_code', auth_code_value)
    return auth_code_value

def createNewToken():
    api_instance = upstox_client.LoginApi()
    api_version = '2.0'
    auth_code = get_auth_code()

    try:
        api_response = api_instance.token(api_version, code=auth_code, client_id=key, client_secret=secret,
                        redirect_uri=redirectURL, grant_type=grant_type)
        # print(api_response)
        access_token = api_response.access_token
        upsert_property('token', access_token)
        return access_token

    except ApiException as e:
        print("Exception when calling LoginApi->token: %s\n" % e)
        # print(api_response.status)

def login():
    configuration = upstox_client.Configuration()
    configuration.access_token = get_property('token')
    api_instance = upstox_client.UserApi(upstox_client.ApiClient(configuration))
    api_version = '2.0'

    try:
        # Get User Fund And Margin
        api_response = api_instance.get_profile(api_version)
        # print(api_response)

        if api_response.status == 'success':
            print("Login Successful.")
            return api_response
    except ApiException as e:
        try:
            createNewToken()
            configuration.access_token = get_property('token')
            api_instance = upstox_client.UserApi(upstox_client.ApiClient(configuration))
            api_response = api_instance.get_profile(api_version)
            if api_response.status == 'success':
                print("Re-login Successful.")
                return api_response
        except ApiException as e:
            print("Exception when calling UserApi->get_user_fund_margin: %s\n" % e)

def getMarketStatus():
    configuration = upstox_client.Configuration()
    login()
    configuration.access_token = get_property('token')
    api_instance = upstox_client.MarketHolidaysAndTimingsApi(upstox_client.ApiClient(configuration))

    try:
        api_response = api_instance.get_market_status("NSE")
        print(api_response.data.status)
    except ApiException as e:
        print("Exception when calling MarketHolidaysAndTimingsApi: %s\n" %e)

def addTodayCandles(symbol: str, candles: list, path= './Data/NSE30/'):
    # Reverse the list so earliest candle comes first
    candles = candles[::-1]

    # Prepare path
    file_path = f'{path}{symbol}.csv'

    # Process and format each candle
    processed_candles = []
    for candle in candles:
        # Convert datetime
        dt = datetime.fromisoformat(candle[0])
        formatted_dt = dt.strftime('%d-%m-%Y %H:%M')

        # Remove last item (Open Interest)
        cleaned_candle = [formatted_dt] + candle[1:-1]

        processed_candles.append(cleaned_candle)

    # Append to CSV
    file_exists = os.path.isfile(file_path)
    with open(file_path, mode='a', newline='') as csvfile:
        writer = csv.writer(csvfile)
        
        # Write header only if file doesn't exist
        if not file_exists:
            writer.writerow(['DateTime', 'Open', 'High', 'Low', 'Close', 'Volume'])
        
        writer.writerows(processed_candles)

    print(f"Appended {len(processed_candles)} candles to {file_path}")
    # addTodayCabdles('SBIN', candles=candles)

def getOHLCVFromFeed(fullFeed):
    symbolKey = list(fullFeed['feeds'].keys())[0]
    tick = fullFeed['feeds'][symbolKey]['fullFeed']['marketFF']['marketOHLC']['ohlc'][1]

    ohlcv = {
        "DateTime" : datetime.fromtimestamp(int(tick['ts']) / 1000).strftime("%d-%m-%Y %H:%M"),
        "Open" : tick['open'],
        "High" : tick['high'],
        "Low" : tick['low'],
        "Close" : tick['close'],
        "Volume" : tick['vol']
    }
    return ohlcv


# getMarketStatus()
# print(getTodayIntradayData('SBIN'))
# addTodayCandles('SBIN', )