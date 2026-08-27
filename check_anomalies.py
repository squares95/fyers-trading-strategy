import pandas as pd

DATA_DIR = r'C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data'

# Check the suspicious early-close days
for sym in ['CGPOWER', 'SUZLON']:
    path = f'{DATA_DIR}/{sym}/{sym}_1MIN.csv'
    df = pd.read_csv(path, parse_dates=['Datetime'])
    df['date'] = df['Datetime'].dt.date
    df['time'] = df['Datetime'].dt.strftime('%H:%M')

    for target_date in ['2024-03-02', '2024-05-18', '2024-11-01', '2021-11-04']:
        day = df[df['date'] == pd.Timestamp(target_date).date()]
        if len(day) > 0:
            print(f"\n{'='*60}")
            print(f"{sym} - {target_date}")
            print(f"Total bars: {len(day)}")
            print(f"First: {day.iloc[0]['Datetime']} Open:{day.iloc[0]['Open']} Close:{day.iloc[0]['Close']}")
            print(f"Last: {day.iloc[-1]['Datetime']} Open:{day.iloc[-1]['Open']} Close:{day.iloc[-1]['Close']}")
            print(f"Day high: {day['High'].max()}, Day low: {day['Low'].min()}")
            print(f"Day change: {day.iloc[-1]['Close'] - day.iloc[0]['Open']:.2f}")
            print(f"Day volume: {day['Volume'].sum():,}")

            # Check day of week
            import datetime
            d = pd.Timestamp(target_date).date()
            print(f"Day of week: {d.strftime('%A')}")
