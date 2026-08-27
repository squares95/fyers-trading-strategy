import pandas as pd
import os

data_dir = r'C:\Users\Tapan\IDirect\my-python-project\src\Fyers\Data'

symbols_to_check = ['BANKNIFTY', 'HDFCBANK', 'NIFTY']
for sym in symbols_to_check:
    fpath = os.path.join(data_dir, sym, f'{sym}_1MIN.csv')
    if os.path.exists(fpath):
        df = pd.read_csv(fpath, parse_dates=['Datetime'])
        dups = df['Datetime'].duplicated().sum()
        print(f"{sym}: {len(df)} rows, range {df['Datetime'].min().date()} to {df['Datetime'].max().date()}, dups={dups}")
    else:
        print(f"{sym}: file not found")
