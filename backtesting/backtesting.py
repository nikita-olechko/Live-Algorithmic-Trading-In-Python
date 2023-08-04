from ib_insync import IB

from backtestingUtilities.simulationUtilities import run_strategy_on_list_of_tickers
from strategies.greaterthan50barsma import sampleSMABuySellStrategy, generate50PeriodSMA_backtest

ib = IB()
try:
    ib.connect('127.0.0.1', 4000, clientId=50)
except Exception:
    print("Could not connect to IBKR. Check that Trader Workstation or IB Gateway is running.")

strategy_name = '50PeriodSMA'
strategy_buy_or_sell_condition_function = sampleSMABuySellStrategy
generate_additional_data_function = generate50PeriodSMA_backtest

run_strategy_on_list_of_tickers(ib, strategy_name,
                                strategy_buy_or_sell_condition_function=strategy_buy_or_sell_condition_function,
                                generate_additional_data_function=generate_additional_data_function,
                                barsize="1 Min", duration="1 D", list_of_tickers=['XOM', 'AAPL', 'MSFT', 'TSLA']
                                )