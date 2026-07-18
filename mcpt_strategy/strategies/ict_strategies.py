"""
ICT Strategy Optimization and Walk-Forward Implementation
"""
import pandas as pd
import numpy as np
from .ict_concepts import (
    ict_order_block_strategy,
    ict_fvg_strategy,
    ict_liquidity_sweep_strategy
)


def optimize_ict_order_block(ohlc: pd.DataFrame) -> tuple:
    """
    Optimize ICT Order Block strategy parameters
    
    Args:
        ohlc: DataFrame with OHLC data
        
    Returns:
        Tuple of (best_params dict, best_profit_factor)
    """
    r = np.log(ohlc['close']).diff().shift(-1)
    
    best_pf = 0
    best_params = {}
    
    ob_lookbacks = [15, 20, 30, 40]
    structure_lookbacks = [5, 10, 15]
    use_fvg_options = [True, False]
    use_sweep_options = [True, False]
    
    for ob_lb in ob_lookbacks:
        for struct_lb in structure_lookbacks:
            for use_fvg in use_fvg_options:
                for use_sweep in use_sweep_options:
                    try:
                        signal = ict_order_block_strategy(
                            ohlc,
                            ob_lookback=ob_lb,
                            structure_lookback=struct_lb,
                            use_fvg=use_fvg,
                            use_sweep=use_sweep
                        )
                        
                        sig_rets = signal * r
                        sig_rets = sig_rets.dropna()
                        
                        if len(sig_rets[sig_rets < 0]) == 0:
                            continue
                        
                        pf = sig_rets[sig_rets > 0].sum() / sig_rets[sig_rets < 0].abs().sum()
                        
                        if pf > best_pf:
                            best_pf = pf
                            best_params = {
                                'ob_lookback': ob_lb,
                                'structure_lookback': struct_lb,
                                'use_fvg': use_fvg,
                                'use_sweep': use_sweep
                            }
                    except:
                        continue
    
    if not best_params:
        best_params = {
            'ob_lookback': 20,
            'structure_lookback': 10,
            'use_fvg': False,
            'use_sweep': False
        }
        best_pf = 1.0
    
    return best_params, best_pf


def optimize_ict_fvg(ohlc: pd.DataFrame) -> tuple:
    """
    Optimize ICT Fair Value Gap strategy parameters
    
    Args:
        ohlc: DataFrame with OHLC data
        
    Returns:
        Tuple of (best_params dict, best_profit_factor)
    """
    r = np.log(ohlc['close']).diff().shift(-1)
    
    best_pf = 0
    best_params = {}
    
    min_gap_mults = [0.3, 0.5, 0.7, 1.0]
    structure_lookbacks = [5, 10, 15, 20]
    use_pd_options = [True, False]
    
    for gap_mult in min_gap_mults:
        for struct_lb in structure_lookbacks:
            for use_pd in use_pd_options:
                try:
                    signal = ict_fvg_strategy(
                        ohlc,
                        min_gap_mult=gap_mult,
                        structure_lookback=struct_lb,
                        use_premium_discount=use_pd
                    )
                    
                    sig_rets = signal * r
                    sig_rets = sig_rets.dropna()
                    
                    if len(sig_rets[sig_rets < 0]) == 0:
                        continue
                    
                    pf = sig_rets[sig_rets > 0].sum() / sig_rets[sig_rets < 0].abs().sum()
                    
                    if pf > best_pf:
                        best_pf = pf
                        best_params = {
                            'min_gap_mult': gap_mult,
                            'structure_lookback': struct_lb,
                            'use_premium_discount': use_pd
                        }
                except:
                    continue
    
    if not best_params:
        best_params = {
            'min_gap_mult': 0.5,
            'structure_lookback': 10,
            'use_premium_discount': False
        }
        best_pf = 1.0
    
    return best_params, best_pf


def optimize_ict_liquidity_sweep(ohlc: pd.DataFrame) -> tuple:
    """
    Optimize ICT Liquidity Sweep strategy parameters
    
    Args:
        ohlc: DataFrame with OHLC data
        
    Returns:
        Tuple of (best_params dict, best_profit_factor)
    """
    r = np.log(ohlc['close']).diff().shift(-1)
    
    best_pf = 0
    best_params = {}
    
    lookbacks = [15, 20, 30, 40]
    sweep_thresholds = [0.0003, 0.0005, 0.001, 0.002]
    confirm_options = [True, False]
    
    for lb in lookbacks:
        for threshold in sweep_thresholds:
            for confirm in confirm_options:
                try:
                    signal = ict_liquidity_sweep_strategy(
                        ohlc,
                        lookback=lb,
                        sweep_threshold=threshold,
                        confirm_structure=confirm
                    )
                    
                    sig_rets = signal * r
                    sig_rets = sig_rets.dropna()
                    
                    if len(sig_rets[sig_rets < 0]) == 0:
                        continue
                    
                    pf = sig_rets[sig_rets > 0].sum() / sig_rets[sig_rets < 0].abs().sum()
                    
                    if pf > best_pf:
                        best_pf = pf
                        best_params = {
                            'lookback': lb,
                            'sweep_threshold': threshold,
                            'confirm_structure': confirm
                        }
                except:
                    continue
    
    if not best_params:
        best_params = {
            'lookback': 20,
            'sweep_threshold': 0.0005,
            'confirm_structure': True
        }
        best_pf = 1.0
    
    return best_params, best_pf


def optimize_ict_hybrid(ohlc: pd.DataFrame) -> tuple:
    """
    Optimize hybrid ICT strategy combining multiple concepts
    
    Args:
        ohlc: DataFrame with OHLC data
        
    Returns:
        Tuple of (best_params dict, best_profit_factor)
    """
    r = np.log(ohlc['close']).diff().shift(-1)
    
    best_pf = 0
    best_params = {}
    
    # Test combinations of ICT concepts
    strategies = ['order_block', 'fvg', 'liquidity_sweep']
    ob_lookbacks = [20, 30]
    fvg_gaps = [0.5, 0.7]
    sweep_lookbacks = [20, 30]
    
    for primary_strategy in strategies:
        for ob_lb in ob_lookbacks:
            for fvg_gap in fvg_gaps:
                for sweep_lb in sweep_lookbacks:
                    try:
                        # Generate signals from each strategy
                        ob_signal = ict_order_block_strategy(
                            ohlc, ob_lookback=ob_lb, 
                            structure_lookback=10,
                            use_fvg=False, use_sweep=False
                        )
                        
                        fvg_signal = ict_fvg_strategy(
                            ohlc, min_gap_mult=fvg_gap,
                            structure_lookback=10,
                            use_premium_discount=True
                        )
                        
                        sweep_signal = ict_liquidity_sweep_strategy(
                            ohlc, lookback=sweep_lb,
                            sweep_threshold=0.0005,
                            confirm_structure=True
                        )
                        
                        # Combine signals based on primary strategy
                        if primary_strategy == 'order_block':
                            signal = ob_signal.copy()
                            # Confirm with FVG or sweep
                            signal[(fvg_signal != ob_signal) & (sweep_signal != ob_signal)] = 0
                        elif primary_strategy == 'fvg':
                            signal = fvg_signal.copy()
                            # Confirm with OB or sweep
                            signal[(ob_signal != fvg_signal) & (sweep_signal != fvg_signal)] = 0
                        else:
                            signal = sweep_signal.copy()
                            # Confirm with OB or FVG
                            signal[(ob_signal != sweep_signal) & (fvg_signal != sweep_signal)] = 0
                        
                        sig_rets = signal * r
                        sig_rets = sig_rets.dropna()
                        
                        if len(sig_rets[sig_rets < 0]) == 0:
                            continue
                        
                        pf = sig_rets[sig_rets > 0].sum() / sig_rets[sig_rets < 0].abs().sum()
                        
                        if pf > best_pf:
                            best_pf = pf
                            best_params = {
                                'primary_strategy': primary_strategy,
                                'ob_lookback': ob_lb,
                                'fvg_gap': fvg_gap,
                                'sweep_lookback': sweep_lb
                            }
                    except:
                        continue
    
    if not best_params:
        best_params = {
            'primary_strategy': 'order_block',
            'ob_lookback': 20,
            'fvg_gap': 0.5,
            'sweep_lookback': 20
        }
        best_pf = 1.0
    
    return best_params, best_pf


def walkforward_ict(
    ohlc: pd.DataFrame,
    strategy_type: str = 'order_block',
    train_lookback: int = 24 * 365 * 4,
    train_step: int = 24 * 30
) -> pd.Series:
    """
    Walk-forward optimization of ICT strategies
    
    Args:
        ohlc: DataFrame with OHLC data
        strategy_type: 'order_block', 'fvg', 'liquidity_sweep', or 'hybrid'
        train_lookback: Number of bars for training
        train_step: Number of bars between reoptimizations
        
    Returns:
        Series with walk-forward signals
    """
    n = len(ohlc)
    wf_signal = pd.Series(np.nan, index=ohlc.index)
    
    next_train = train_lookback
    current_params = None
    tmp_signal = None
    
    for i in range(train_lookback, n):
        if i == next_train:
            print(f"Optimizing {strategy_type} at bar {i}/{n} ({i/n*100:.1f}%)", end='\r')
            
            train_data = ohlc.iloc[i-train_lookback:i]
            
            if strategy_type == 'order_block':
                best_params, _ = optimize_ict_order_block(train_data)
                tmp_signal = ict_order_block_strategy(ohlc, **best_params)
            elif strategy_type == 'fvg':
                best_params, _ = optimize_ict_fvg(train_data)
                tmp_signal = ict_fvg_strategy(ohlc, **best_params)
            elif strategy_type == 'liquidity_sweep':
                best_params, _ = optimize_ict_liquidity_sweep(train_data)
                tmp_signal = ict_liquidity_sweep_strategy(ohlc, **best_params)
            elif strategy_type == 'hybrid':
                best_params, _ = optimize_ict_hybrid(train_data)
                # Reconstruct hybrid signal
                ob_signal = ict_order_block_strategy(
                    ohlc, ob_lookback=best_params['ob_lookback'],
                    structure_lookback=10, use_fvg=False, use_sweep=False
                )
                fvg_signal = ict_fvg_strategy(
                    ohlc, min_gap_mult=best_params['fvg_gap'],
                    structure_lookback=10, use_premium_discount=True
                )
                sweep_signal = ict_liquidity_sweep_strategy(
                    ohlc, lookback=best_params['sweep_lookback'],
                    sweep_threshold=0.0005, confirm_structure=True
                )
                
                primary = best_params['primary_strategy']
                if primary == 'order_block':
                    tmp_signal = ob_signal.copy()
                    tmp_signal[(fvg_signal != ob_signal) & (sweep_signal != ob_signal)] = 0
                elif primary == 'fvg':
                    tmp_signal = fvg_signal.copy()
                    tmp_signal[(ob_signal != fvg_signal) & (sweep_signal != fvg_signal)] = 0
                else:
                    tmp_signal = sweep_signal.copy()
                    tmp_signal[(ob_signal != sweep_signal) & (fvg_signal != sweep_signal)] = 0
            
            current_params = best_params
            next_train += train_step
        
        if tmp_signal is not None:
            wf_signal.iloc[i] = tmp_signal.iloc[i]
    
    print()
    return wf_signal
