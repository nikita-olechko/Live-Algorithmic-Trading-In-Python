import inspect
import re
import pandas as pd
import os
import gc
from ib_insync import util, Contract


# from backtesting.simulations import customOrders


def run_strategy_on_list_of_tickers(ib, strategy, strategy_buy_or_sell_condition_function,
                                    generate_additional_data_function=None,
                                    barsize="1 day", duration="3 Y", what_to_show="TRADES", list_of_tickers=None,
                                    strategy_period_offset=20, *args, **kwargs):
    if list_of_tickers is None:
        list_of_tickers = pd.read_csv("../backtesting/nyse-listed.csv")['ACT Symbol']
    try:
        erred_tickers = pd.read_csv("../backtesting/data/ErroredTickers/nyse-listed.csv", header=False,
                                    names=['Ticker'])
    except:
        erred_tickers = pd.DataFrame(columns=['Ticker'])
    folder_path = os.path.join(os.getcwd(), "../backtesting/data", "Strategy Results")
    summary_file_path_name = os.path.join(folder_path,
                                          f"{strategy.replace(' ', '')}{barsize.replace(' ', '')}{duration.replace(' ', '')}.csv")
    if os.path.exists(summary_file_path_name):
        all_tickers_summary = pd.read_csv(summary_file_path_name)
    else:
        all_tickers_summary = pd.DataFrame()

    completed_tickers = all_tickers_summary['ticker'].unique() if 'ticker' in all_tickers_summary.columns else []
    list_of_tickers = [ticker for ticker in list_of_tickers if
                       ticker not in completed_tickers and ticker not in erred_tickers['Ticker'].values]

    for ticker in list_of_tickers:
        gc.collect()
        stk_data = retrieve_base_data(ib, ticker, barsize=barsize, duration=duration)

        if stk_data is not None:
            summary_df = simulate_trading_on_strategy(stk_data, ticker, strategy_buy_or_sell_condition_function,
                                                      generate_additional_data_function=generate_additional_data_function,
                                                      barsize=barsize, duration=duration,
                                                      strategy_period_offset=strategy_period_offset, *args, **kwargs)
            all_tickers_summary = pd.concat([all_tickers_summary, summary_df])
            all_tickers_summary.to_csv(summary_file_path_name, index=False)


def simulate_trading_on_strategy(stk_data, ticker, strategy_buy_or_sell_condition_function,
                                 generate_additional_data_function=None,
                                 barsize="1 day", duration="1 Y", strategy_period_offset=20, *args, **kwargs):
    if generate_additional_data_function is not None:
        for i in range(len(stk_data)):
            stk_data.iloc[:i + 1] = generate_additional_data_function(stk_data.iloc[:i + 1], *args, **kwargs)

    last_order_index = 0

    # Remove NA values
    stk_data = stk_data.dropna()

    for index in range(strategy_period_offset, len(stk_data)):
        # Get order based on strategy conditions
        order = strategy_buy_or_sell_condition_function(stk_data, ticker, index, last_order_index, *args, **kwargs)

        # If this is the first order, wait until first Buy order to establish the position
        if last_order_index == 0:
            if order == 1:
                stk_data.loc[index, 'Orders'] = 1
                stk_data.loc[index, 'Position'] = - stk_data.loc[index, ticker]
                last_order_index = index
        else:
            stk_data, last_order_index = order_selector(order)(stk_data, index, last_order_index, ticker)

        # If the last order was a buy, sell the position
        if index == len(stk_data) - 1 and stk_data.loc[last_order_index, 'Orders'] == 1:
            stk_data.loc[index, 'Orders'] = -1
            last_order_index = index
            stk_data.loc[index, 'Position'] = stk_data.loc[index - 1, 'Position'] + stk_data.loc[index, ticker]

    summary_df = create_summary_data(stk_data, ticker)
    return summary_df


def create_summary_data(stk_data, ticker, summary_df=None):
    ticker_wap = f"{ticker}.WAP"
    stk_data['holdingGrossReturn'] = stk_data[ticker_wap] / stk_data[ticker_wap].iloc[0]

    trade_completed_indices = stk_data[stk_data['Orders'] == -1].index
    final_position = stk_data['Position'].iloc[-1]
    average_position_post_trade = stk_data['Position'].loc[trade_completed_indices].mean()
    sd_position_post_trade = stk_data['Position'].loc[trade_completed_indices].std()
    max_position_post_trade = stk_data['Position'].loc[trade_completed_indices].max()
    min_position_post_trade = stk_data['Position'].loc[trade_completed_indices].min()

    changes_in_position_per_trade = stk_data['Position'].loc[trade_completed_indices].diff().dropna()

    average_change_in_position_per_trade = changes_in_position_per_trade.mean()
    sd_change_in_position_per_trade = changes_in_position_per_trade.std()
    min_change_in_position_per_trade = changes_in_position_per_trade.min()
    max_change_in_position_per_trade = changes_in_position_per_trade.max()

    final_holding_gross_return = stk_data['holdingGrossReturn'].iloc[-1]
    average_holding_gross_return = stk_data['holdingGrossReturn'].mean()
    sd_holding_gross_return = stk_data['holdingGrossReturn'].std()
    min_holding_gross_return = stk_data['holdingGrossReturn'].min()
    max_holding_gross_return = stk_data['holdingGrossReturn'].max()

    new_summary = pd.DataFrame({
        'ticker': [ticker],
        'finalPosition': [final_position],
        'AveragePosition': [average_position_post_trade],
        'SDPosition': [sd_position_post_trade],
        'MaxPosition': [max_position_post_trade],
        'MinPosition': [min_position_post_trade],
        'AvgChangeInPosition': [average_change_in_position_per_trade],
        'SDChangeInPosition': [sd_change_in_position_per_trade],
        'MinChangeInPosition': [min_change_in_position_per_trade],
        'MaxChangeInPosition': [max_change_in_position_per_trade],
        'FinalHoldingGrossReturn': [final_holding_gross_return],
        'AverageHoldingGrossReturn': [average_holding_gross_return],
        'SDHoldingGrossReturn': [sd_holding_gross_return],
        'MinHoldingGrossReturn': [min_holding_gross_return],
        'MaxHoldingGrossReturn': [max_holding_gross_return]
    })

    if summary_df is not None:
        new_summary = pd.concat([summary_df, new_summary])

    return new_summary


def retrieve_base_data(ib, ticker, barsize="1 day", duration="3 Y", what_to_show="TRADES"):
    stk_data = get_stock_data(ib, ticker, barsize=barsize, duration=duration, what_to_show=what_to_show)
    # fix, should not work atm as cannot find the file
    if stk_data is None:
        csv_file_path = "../backtesting/data/ErroredTickers/ErroredTickers.csv"
        try:
            erred_tickers = pd.read_csv(csv_file_path)
        except FileNotFoundError:
            erred_tickers = pd.DataFrame(columns=['Ticker'])
        erred_tickers = pd.concat([erred_tickers, pd.DataFrame({'Ticker': [ticker]})], ignore_index=True)
        erred_tickers.to_csv(csv_file_path, index=False)

    return stk_data


def get_stock_data(ib, ticker, barsize='1 min', duration='1 M', what_to_show='TRADES'):
    contract = Contract()
    contract.symbol = ticker
    contract.secType = 'STK'
    contract.exchange = 'SMART'
    contract.currency = 'USD'
    contract.primaryExchange = 'NYSE'
    ticker = contract.symbol
    file_name = create_historical_data_file_name(ticker, barsize, duration)
    folder_path = os.path.join(os.getcwd(), "../backtesting/data", "Historical Data")

    # If the data already exists, retrieve it
    if os.path.isfile(os.path.join(folder_path, file_name)):
        try:
            stk_data = pd.read_csv(os.path.join(folder_path, file_name), parse_dates=True, index_col=0)
        except Exception as e:
            print("An error occurred:", str(e))
            stk_data = None
    else:
        stk_data = None
        try:
            bars = ib.reqHistoricalData(
                contract,
                endDateTime='',
                durationStr=duration,
                barSizeSetting=barsize,
                whatToShow=what_to_show,
                useRTH=True,
                formatDate=1)
            stk_data = util.df(bars)
            stk_data.columns = stk_data.columns.str.title()
            # if new data acquired, write it to the historical data folder
            if len(stk_data) <= 50:
                return None
            stk_data = add_analysis_data_to_historical_data(stk_data, ticker)
            stk_data.to_csv(os.path.join(folder_path, file_name))
            print("Historical Data Created")
        except Exception as e:
            print("An error occurred:", str(e))
            return None
    return stk_data


def add_analysis_data_to_historical_data(stk_data, ticker):
    stk_data["Orders"] = 0
    stk_data["Position"] = 0
    return stk_data


def create_historical_data_file_name(ticker, barsize, duration):
    file_ticker = ticker.replace(" ", "")
    file_barsize = barsize.replace(" ", "")
    file_duration = duration.replace(" ", "")
    filename = f"Historical{file_ticker}{file_barsize}{file_duration}"
    return filename


def order_selector(order):
    order = str(order)
    order_dict = {
        "1": buy_order,
        "-1": sell_order,
        "2": hold_order,
        "0": nothing_order
    }
    return order_dict[order]


def buy_order(stk_data, index, last_order_index, ticker_wap):
    stk_data.at[index, 'Orders'] = 1
    last_order_index = index
    stk_data.at[index, 'Position'] = stk_data.at[index - 1, 'Position'] - stk_data.at[index, ticker_wap]
    return stk_data, last_order_index


def sell_order(stk_data, index, last_order_index, ticker_wap):
    stk_data.at[index, 'Orders'] = -1
    last_order_index = index
    stk_data.at[index, 'Position'] = stk_data.at[index - 1, 'Position'] + stk_data.at[index, ticker_wap]
    return stk_data, last_order_index


def hold_order(stk_data, index, last_order_index):
    stk_data.at[index, 'Orders'] = 2
    stk_data.at[index, 'Position'] = stk_data.at[index - 1, 'Position']
    return stk_data, last_order_index


def nothing_order(stk_data, index, last_order_index):
    stk_data.at[index, 'Position'] = stk_data.at[index - 1, 'Position']
    return stk_data, last_order_index
