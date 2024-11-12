import lzma
import dill as pickle

def load_pickle(path):
    with lzma.open(path, 'rb') as fp:
        file = pickle.load(fp)
    return file

def save_pickle(path, obj):
    with lzma.open(path, 'wb') as fp:
        pickle.dump(obj, fp)
    

def get_pnl_stats(date, prev, portfolio_df, insts, idx, dfs):
    day_pnl = 0
    nominal_ret = 0

    for inst in insts:
        units = portfolio_df.loc[idx-1, "{} units".format(inst)]
        if(units != 0):
            delta = dfs[inst].loc[date, 'close'] - dfs[inst].loc[prev, 'close']
            inst_pnl = units * delta
            day_pnl += inst_pnl
            nominal_ret += portfolio_df.loc[idx-1, "{} w".format(inst)] * dfs[inst].loc[date, 'ret']
    
    capital_ret = nominal_ret*portfolio_df.loc[idx-1, 'leverage']
    portfolio_df.loc[idx, 'capital'] =  portfolio_df.loc[idx-1, 'capital'] + day_pnl

    portfolio_df.loc[idx, 'day_pnl'] = day_pnl 
    portfolio_df.loc[idx, 'nominal_ret'] = nominal_ret 
    portfolio_df.loc[idx, 'capital_ret'] = capital_ret 
    
    return day_pnl, capital_ret
                
    
import numpy as np
import pandas as pd

from copy import deepcopy
    
class AbstractImplementationException(Exception):
    pass

class Alpha():

    def __init__(self, insts, dfs, start, end):
        self.insts = insts
        self.dfs = deepcopy(dfs)
        self.start = start
        self.end = end

    def init_portfolio_settings(self, trade_range):
        portfolio_df = pd.DataFrame(index=trade_range)\
        .reset_index()\
        .rename(columns={'index': 'datetime'})

        portfolio_df.loc[0, "capital"] = 10000

        return portfolio_df

    def pre_compute(self, trade_range):
        pass

    def post_compute(self, trade_range):
        pass

    def compute_signal_distribution(self, eligibles, date):
        raise AbstractImplementationException("no concrete implementation for signal generation")

    def compute_meta_info(self, trade_range):

        self.pre_compute(trade_range=trade_range)
        
        for inst in self.insts:
            df = pd.DataFrame(index=trade_range)            
            self.dfs[inst] = df.join(self.dfs[inst]).ffill().bfill()           
            self.dfs[inst]['ret'] = -1 + self.dfs[inst]['close']/self.dfs[inst]['close'].shift(1)            
            sampled = self.dfs[inst]['close'] != self.dfs[inst]['close'].shift(1).bfill()
            eligible = sampled.rolling(5).apply(lambda x: int(np.any(x))).fillna(0)            
            self.dfs[inst]['eligible'] = eligible.astype(int) & (self.dfs[inst]['close'] > 0).astype(int)
        
        self.post_compute(trade_range=trade_range)
        return


    def run_simulation(self):
        
        print("running tests")
        date_range = pd.date_range(self.start, self.end, freq='D')
        self.compute_meta_info(trade_range=date_range)
        portfolio_df = self.init_portfolio_settings(trade_range=date_range)

        for i in portfolio_df.index:
            date = portfolio_df.loc[i, 'datetime']

            eligibles = [inst for inst in self.insts if self.dfs[inst].loc[date, 'eligible']]
            non_eligibles = [inst for inst in self.insts if inst not in eligibles]

            if i != 0:
                #compute pnl
                date_prev = portfolio_df.loc[i-1, 'datetime']
                day_pnl, capital_ret = get_pnl_stats(
                    date = date, 
                    prev = date_prev, 
                    portfolio_df = portfolio_df, 
                    insts=self.insts, 
                    idx=i, 
                    dfs=self.dfs
                )

            forecasts, forecast_chips = self.compute_signal_distribution(eligibles, date)

            for inst in non_eligibles:
                portfolio_df.loc[i, "{} w".format(inst)] = 0     
                portfolio_df.loc[i, "{} units".format(inst)] = 0        

            nominal_tot = 0

            for inst in eligibles:
                forecast = forecasts[inst]
                dollar_allocation = portfolio_df.loc[i, 'capital']/forecast_chips if forecast_chips != 0 else 0
                position = forecast * dollar_allocation/self.dfs[inst].loc[date, 'close']
                portfolio_df.loc[i, inst + " units"] = position
                nominal_tot += abs(position*self.dfs[inst].loc[date, 'close'])
            
            for inst in eligibles:
                units = portfolio_df.loc[i, inst + " units"]
                nominal_inst = units*self.dfs[inst].loc[date, 'close']
                inst_w = nominal_inst/nominal_tot
                portfolio_df.loc[i, inst + " w"] = inst_w
            
            portfolio_df.loc[i, 'nominal'] = nominal_tot
            portfolio_df.loc[i, 'leverage'] = nominal_tot/portfolio_df.loc[i, 'capital']

            if i%100==0: print(portfolio_df.loc[i])

        return portfolio_df
