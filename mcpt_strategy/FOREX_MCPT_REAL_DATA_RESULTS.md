# Forex Strategy MCPT on REAL FOREX DATA - Complete Results

## Executive Summary

**CRITICAL FINDING**: The forex strategy **FAILS MCPT on all 4 currency pairs** when tested on real Dukascopy data from 2016-2024.

This is the **definitive test** the strategy was designed for - real forex data, multiple pairs, proper MCPT validation.

---

## Test Configuration

### Data Source
- **Provider**: Dukascopy (institutional-grade forex data)
- **Timeframe**: 4-hour candles
- **Period**: 2016-01-03 to 2024-12-31 (9 years)
- **Pairs**: EUR/USD, GBP/USD, USD/JPY, AUD/USD
- **Total Bars**: ~14,500 per pair

### Strategy
- **Type**: Sniper component from dual forex strategy
- **EMA Fast/Slow**: 3/9
- **ADX Threshold**: 15.0
- **DI Filter**: Enabled (+DI vs -DI directional confirmation)

### MCPT Settings
- **Permutations**: 100
- **Method**: Bar-by-bar shuffling (neurotrader888 methodology)
- **Significance Threshold**: p < 0.01
- **Metric**: Profit Factor

---

## Results by Pair

### 1. EUR/USD (Best Performer)

**Real Performance:**
```
Profit Factor:     1.18
Total Return:      +6.86%
Sharpe Ratio:      0.09
Max Drawdown:      -2.56%
Win Rate:          2.5%
Trades:            1,420
```

**MCPT Results:**
```
Real PF:           1.1762
Mean Permuted PF:  1.0096 (± 0.1189)
P-Value:           0.09
Permutations Better: 8/99
Status:            ✗ FAIL (need p < 0.01)
```

**Analysis**: 
- Only profitable pair in the test
- Real PF is better than 91% of permutations
- **But** p-value of 0.09 is 9× above threshold
- Close to significance but not enough

---

### 2. GBP/USD (Marginal)

**Real Performance:**
```
Profit Factor:     1.05
Total Return:      +2.40%
Sharpe Ratio:      0.02
Max Drawdown:      -5.89%
Win Rate:          2.5%
Trades:            1,366
```

**MCPT Results:**
```
Real PF:           1.0487
Mean Permuted PF:  0.9975 (± 0.1025)
P-Value:           0.30
Permutations Better: 29/99
Status:            ✗ FAIL
```

**Analysis**:
- Barely profitable (PF 1.05)
- Real PF only slightly above permuted mean
- P-value 0.30 = 30× above threshold
- No statistical significance

---

### 3. USD/JPY (Unprofitable)

**Real Performance:**
```
Profit Factor:     0.97 ❌
Total Return:      -1.39%
Sharpe Ratio:      -0.02
Max Drawdown:      -6.56%
Win Rate:          2.4%
Trades:            1,384
```

**MCPT Results:**
```
Real PF:           0.9724
Mean Permuted PF:  1.0020 (± 0.1149)
P-Value:           0.60
Permutations Better: 59/99
Status:            ✗ FAIL
```

**Analysis**:
- Net loss (PF < 1.0)
- 60% of permutations performed better
- Strategy is **worse than random** on this pair

---

### 4. AUD/USD (Worst Performer)

**Real Performance:**
```
Profit Factor:     0.91 ❌
Total Return:      -5.45%
Sharpe Ratio:      -0.06
Max Drawdown:      -14.10%
Win Rate:          2.5%
Trades:            1,464
```

**MCPT Results:**
```
Real PF:           0.9114
Mean Permuted PF:  1.0063 (± 0.0980)
P-Value:           0.85
Permutations Better: 84/99
Status:            ✗ FAIL
```

**Analysis**:
- Significant net loss
- 85% of permutations performed better
- Strategy is **significantly worse than random**
- Would have lost 5.45% over 9 years

---

## Multi-Pair Summary

| Pair | Real PF | P-Value | Return | Status |
|------|---------|---------|--------|--------|
| **EUR/USD** | 1.18 | 0.09 | +6.86% | ✗ FAIL |
| **GBP/USD** | 1.05 | 0.30 | +2.40% | ✗ FAIL |
| **USD/JPY** | 0.97 | 0.60 | -1.39% | ✗ FAIL |
| **AUD/USD** | 0.91 | 0.85 | -5.45% | ✗ FAIL |
| **TOTAL** | - | - | - | **0/4 PASS** |

**Pass Rate: 0%**

---

## What Does This Mean?

### 1. The Strategy Does NOT Pass MCPT

Even on real forex data (its intended market), the strategy fails the strict MCPT test on all pairs.

- **Best p-value**: 0.09 (EUR/USD) - still 9× too high
- **Worst p-value**: 0.85 (AUD/USD) - strategy is worse than random
- **Average p-value**: 0.46 - no statistical significance

### 2. Performance is Inconsistent Across Pairs

- **1 profitable pair** (EUR/USD: +6.86%)
- **1 marginal pair** (GBP/USD: +2.40%)
- **2 unprofitable pairs** (USD/JPY: -1.39%, AUD/USD: -5.45%)

This suggests the strategy is **not robust** - it works on some pairs but fails on others.

### 3. Comparison with Original Validation

| Metric | Original (2018-2025) | This Test (2016-2024) |
|--------|---------------------|----------------------|
| **Data** | Real forex | Real forex ✓ |
| **Pairs** | 4 major pairs | Same 4 pairs ✓ |
| **Return** | +13.6% | +0.61% (avg) |
| **Profit Factor** | 1.98 | 1.05 (avg) |
| **Max DD** | 4.7% | 7.28% (avg) |
| **Validation** | Multi-era ✓ | MCPT ✗ |

**The original validation was more favorable**, possibly because:
1. Different time period (2018-2025 vs 2016-2024)
2. Multi-era validation is less strict than MCPT
3. Strategy may have been optimized for 2018+ period
4. 2016-2017 was a difficult period for this strategy

---

## Key Insights

### ✅ What This Test Proves

1. **MCPT is Working Correctly**
   - Proper distribution of permuted profit factors
   - Correct p-value calculation
   - Successfully tested on real market data

2. **Market-Specific is Insufficient**
   - Testing on the "right" market (forex) isn't enough
   - Strategy still needs statistical edge
   - MCPT is **stricter** than multi-era validation

3. **The Strategy Has Limited Edge**
   - Only 1/4 pairs is solidly profitable
   - EUR/USD shows some edge (p=0.09) but not enough
   - Other pairs are marginal or unprofitable

### ⚠️ What This Means for Trading

1. **Original Validation May Be Optimistic**
   - +13.6% return and PF 1.98 may not generalize
   - Could be period-specific (2018-2025)
   - Multi-era validation missed some overfitting

2. **Strategy is Not Robust**
   - Works on EUR/USD, fails on AUD/USD
   - Inconsistent across similar instruments
   - Raises concerns about forward performance

3. **MCPT is Very Strict**
   - Passing MCPT with p < 0.01 is HARD
   - Only 1% of random strategies would pass
   - High bar for statistical significance

---

## Why The Difference from Original Results?

### Possible Explanations:

1. **Time Period Matters**
   - Original: 2018-2025 (post-crisis, QE era)
   - This test: 2016-2024 (includes 2016-2017 drawdown)
   - EUR/USD had different characteristics pre-2018

2. **Optimization Period**
   - Strategy may have been optimized on 2020+ data
   - Then validated on 2021-2025 (walk-forward)
   - Earlier period (2016-2019) wasn't used in optimization

3. **Validation Method**
   - Multi-era: Tests consistency across time periods
   - MCPT: Tests statistical significance vs randomness
   - Both valid, but MCPT is stricter

4. **Portfolio vs Individual**
   - Original tested as portfolio of 4 pairs
   - This test shows individual pair performance
   - Portfolio diversification may hide weak pairs

---

## Recommendations

### If You Want to Use This Strategy

**Pros:**
- Works reasonably on EUR/USD (PF 1.18, +6.86%)
- Based on sound technical principles
- Original validation showed good results

**Cons:**
- Fails MCPT on all pairs (including EUR/USD)
- Loses money on USD/JPY and AUD/USD
- Not statistically significant
- May have been curve-fit to 2018-2025

**Verdict**: **Use with caution**
- Consider EUR/USD only
- Use small position sizes
- Monitor closely for regime changes
- Be prepared for 6%+ drawdowns
- Accept that edge is marginal

### If You Want MCPT-Passing Strategies

Based on extensive testing (crypto synthetic, crypto strategies, ICT strategies, confluence strategies, and now forex on real data):

**MCPT is VERY difficult to pass:**
- Requires strong, consistent edge
- Must work after bar shuffling (no temporal patterns)
- p < 0.01 threshold is strict
- Most "working" strategies fail MCPT

**Options:**
1. **Accept multi-era validation** (what original strategy used)
2. **Build strategies specifically for MCPT** (may sacrifice real-world performance)
3. **Combine both methods** (multi-era + MCPT for extra confidence)
4. **Use real data from start** (synthetic data doesn't work for validation)

### If You're Building New Strategies

**Lessons Learned:**
1. ✅ Test on real data (synthetic isn't enough)
2. ✅ Test on multiple instruments
3. ✅ Test on multiple time periods
4. ✅ Use multiple validation methods
5. ⚠️ Don't expect MCPT to always pass
6. ⚠️ MCPT is one tool, not the only tool

---

## Technical Details

### Data Fetching
```python
# Successfully fetched from Dukascopy
# 4H data, 2016-2024, 4 major pairs
# ~14,500 bars per pair
# Institutional quality data
```

### Permutation Method
```python
# Bar-by-bar shuffling (neurotrader888 method)
# Preserves OHLC relationships within bars
# Destroys temporal patterns
# Creates random but realistic price paths
```

### Files Generated
```
/workspace/mcpt_strategy/data/forex_cache/
  ├── EURUSD_2016_2024_4h.parquet (cached)
  ├── GBPUSD_2016_2024_4h.parquet
  ├── USDJPY_2016_2024_4h.parquet
  └── AUDUSD_2016_2024_4h.parquet

/workspace/mcpt_strategy/results/
  ├── forex_mcpt_real_data.json (full results)
  └── forex_mcpt_real_multipair.png (visualization)
```

---

## Conclusion

### The Bottom Line

**The forex strategy DOES NOT pass MCPT when tested on real forex data from 2016-2024.**

This is the most definitive test we've run:
- ✅ Real data (not synthetic)
- ✅ Correct market (forex, not crypto)
- ✅ Multiple pairs (4 majors)
- ✅ Long period (9 years)
- ✅ Proper MCPT implementation
- ❌ Does not pass (0/4 pairs)

**However, this does NOT mean the strategy is useless:**
- EUR/USD shows some profitability (+6.86%)
- Original multi-era validation was positive
- May work in specific market conditions
- MCPT is very strict (many "working" strategies fail)

**Recommendation**: Use the strategy with **realistic expectations**:
- Edge is marginal, not strong
- Works better on some pairs (EUR/USD)
- May be period-specific (2018-2025)
- Requires careful risk management
- May not pass strict statistical tests

**For researchers**: This demonstrates that **MCPT and multi-era validation can disagree** - the strategy passed multi-era but failed MCPT. This is valuable information about the limits and trade-offs of different validation methods.

---

## Next Steps

1. **If using this strategy**: Focus on EUR/USD, use small sizes, monitor closely
2. **If building new strategies**: Use both MCPT and multi-era validation
3. **If doing research**: Consider why the two methods disagreed
4. **If skeptical**: This is healthy - always question backtests
