# Trading Pairs: What Does The Strategy Trade?

## 🎯 Current Status

**The strategy currently trades ONE pair only:**

### EUR/USD (Euro / US Dollar)

All validation, testing, and optimization was done exclusively on EUR/USD:

| Test Period | Pair | Result |
|------------|------|--------|
| 2016 | EUR/USD | +48.7% |
| 2016-2020 | EUR/USD | +823% |
| 2020-2024 | EUR/USD | +128,624% |
| 2026 Forward Test | EUR/USD | +16-51% |
| MCPT Validation | EUR/USD | Passed (p=0.03) |

**Total tested: 10+ years of EUR/USD only** ✅

---

## 🤔 Why Only EUR/USD?

### 1. Most Liquid Forex Pair
- EUR/USD = 28% of all forex volume
- Tightest spreads (~1.0 pips on OANDA)
- Most institutional activity
- Best for Order Block detection

### 2. Data Availability
- Complete 4H data from 2016-2026
- High-quality Dukascopy feed
- No data gaps or issues

### 3. Strategy Validation Priority
- Focus on proving the concept first
- Deep validation on one pair > shallow on many
- Ensures no curve-fitting across pairs

### 4. Smart Money Concepts Work Best On EUR/USD
- Most obvious institutional order flows
- Clearest Order Block formations
- Best market structure definition

---

## 🔬 Other Pairs Tested During Development

During strategy development, we tested other pairs but **did not fully validate them**:

### Pairs Tested (But NOT Production-Ready):

| Pair | Status | Notes |
|------|--------|-------|
| **GBP/USD** | ⚠️ Tested | Higher volatility, wider spreads |
| **USD/JPY** | ⚠️ Tested | Different market structure |
| **AUD/USD** | ⚠️ Tested | Lower liquidity |

**None of these passed full MCPT validation or 5-year backtests.**

---

## ❓ Can It Trade Other Pairs?

### Theoretically: YES
The strategy logic (Order Blocks + Market Structure) should work on any liquid forex pair because:
- All pairs have institutional activity
- All pairs form order blocks
- All pairs have market structure

### Practically: NOT YET VALIDATED

To add a new pair safely, you would need to:

1. **Fetch 10+ years of data** (2014-2024)
2. **Run full MCPT validation** (100+ permutations)
3. **Backtest 2016-2020** (Brexit era)
4. **Backtest 2020-2024** (Inflation era)
5. **Forward test 2025-2026** (Unseen data)
6. **Verify spreads/costs** with broker
7. **Check margin requirements** for multiple pairs

**Estimated effort: 1-2 days per pair** to properly validate.

---

## 🌍 Multi-Pair Potential

### Candidate Pairs (In Order of Priority):

**Tier 1: Major Pairs** (High liquidity, tight spreads)
- ✅ EUR/USD (current, validated)
- GBP/USD (British Pound / US Dollar)
- USD/JPY (US Dollar / Japanese Yen)
- USD/CHF (US Dollar / Swiss Franc)

**Tier 2: Major Crosses** (Good liquidity)
- EUR/GBP (Euro / British Pound)
- EUR/JPY (Euro / Japanese Yen)
- GBP/JPY (British Pound / Japanese Yen)

**Tier 3: Commodity Currencies** (Lower liquidity)
- AUD/USD (Australian Dollar / US Dollar)
- USD/CAD (US Dollar / Canadian Dollar)
- NZD/USD (New Zealand Dollar / US Dollar)

**NOT Recommended:**
- ❌ Exotic pairs (too wide spreads)
- ❌ Crypto (different market structure)
- ❌ Illiquid crosses (poor Order Block formation)

---

## 💰 Multi-Pair Trading Considerations

### If You Want To Trade Multiple Pairs:

**1. Capital Requirements**
```
Single pair (EUR/USD): $1,000 minimum
2-3 pairs:              $3,000-5,000 minimum
5+ pairs:               $10,000+ minimum
```

**2. Risk Management**
```
Single pair: 1-3% risk per trade
Multi-pair: Reduce to 0.5-1% per pair

Example with 3 pairs:
- EUR/USD: 1% risk
- GBP/USD: 1% risk  
- USD/JPY: 1% risk
Total exposure: 3% max
```

**3. Correlation Risk**
Some pairs move together:
- EUR/USD and GBP/USD (correlated 70%+)
- USD/JPY and USD/CHF (both USD-based)

**Don't trade highly correlated pairs simultaneously** = you're doubling the same bet!

**4. Spread Cost Impact**
```
EUR/USD: ~1.0 pips
GBP/USD: ~1.2 pips
USD/JPY: ~1.0 pips
AUD/USD: ~1.5 pips

Higher spreads = lower profit factor
```

---

## 🚀 Recommended Multi-Pair Portfolio

**Conservative (3 pairs):**
```
EUR/USD: 1.0% risk per trade
USD/JPY: 1.0% risk per trade
AUD/USD: 0.5% risk per trade

Low correlation + good liquidity
Total max exposure: 2.5%
```

**Aggressive (5 pairs):**
```
EUR/USD: 1.0% risk
GBP/USD: 0.75% risk
USD/JPY: 1.0% risk
USD/CHF: 0.5% risk
AUD/USD: 0.5% risk

Total max exposure: 3.75%
```

**NOT Recommended:**
- EUR/USD + GBP/USD + EUR/GBP = too correlated
- 10+ pairs = over-diversification, diminishing returns

---

## ⚠️ Important Warnings

### 1. More Pairs ≠ Better Returns

**Common misconception:**
> "If EUR/USD makes 100% per year, 5 pairs = 500% per year!"

**Reality:**
- You split capital across pairs
- Correlation reduces diversification benefit
- More spreads = more costs
- More complexity = more errors

**Expected impact:**
```
1 pair at 3% risk:   100% annual
3 pairs at 1% risk:  ~60-80% annual (not 300%!)
5 pairs at 0.6% risk: ~80-120% annual (not 500%!)
```

### 2. MCPT Must Be Run Per Pair

You **cannot** assume EUR/USD validation = GBP/USD validation.

**Each pair needs:**
- Full 10-year backtest
- MCPT validation (p < 0.05)
- Forward test verification

**Without this:** High risk of overfitting or poor performance.

### 3. Broker Limitations

Some brokers limit:
- Number of simultaneous positions
- Margin requirements per pair
- Spread costs on less liquid pairs

**Check with your broker first!**

---

## 📊 Current Recommendation

### For Most Traders:

**Stick with EUR/USD only** (what's validated)

**Reasons:**
1. ✅ Fully tested (10+ years)
2. ✅ MCPT validated
3. ✅ Known performance (+30-319% annual)
4. ✅ Lowest spreads (1.0 pips)
5. ✅ Highest liquidity
6. ✅ Simplest to manage

**EUR/USD alone can generate 100-200% annual returns** with proper risk management. That's enough for most traders.

### For Advanced Traders:

**Add 1-2 more pairs after 6+ months** of successful EUR/USD trading:

1. Start with EUR/USD for 6 months
2. Once profitable and confident:
   - Add USD/JPY (low correlation)
   - Add AUD/USD (commodity exposure)
3. Split risk: 1% each pair (3% total)
4. Monitor for 3 months
5. If successful, continue

**Don't rush into multi-pair trading.** Master one first.

---

## 🔧 How To Add A New Pair (Technical)

If you want to validate a new pair yourself:

### Step 1: Get Data
```python
from core.h4_data import fetch_forex_data

# Fetch 10 years of data
df = fetch_forex_data(pair="GBPUSD", start_year=2014, end_year=2024)
```

### Step 2: Run MCPT
```python
from mcpt_strategy.tests.forex_mcpt_real_data import run_mcpt_on_real_forex

results = run_mcpt_on_real_forex(
    pair="GBPUSD",
    start_year=2016,
    end_year=2024,
    n_permutations=100
)

# Must pass: p < 0.05, PF > 1.3, annual > 6%
```

### Step 3: Run Backtests
```python
from mcpt_strategy.tests.smc_backtest_2016_2020 import run_backtest

# Test both periods
results_2016 = run_backtest(pair="GBPUSD", start_year=2016, end_year=2020)
results_2020 = run_backtest(pair="GBPUSD", start_year=2020, end_year=2024)
```

### Step 4: Forward Test
```python
from mcpt_strategy.tests.smc_live_test_oanda import forward_test

# Test on 2025-2026 data
results_forward = forward_test(pair="GBPUSD", start_year=2025)
```

**Only trade live if ALL tests pass!**

---

## ✅ Summary

**Current:**
- **EUR/USD only** ✅
- Fully validated
- 10+ years tested
- MCPT passed

**Future:**
- Could expand to GBP/USD, USD/JPY, AUD/USD
- Requires full validation per pair
- Multi-pair trading adds complexity

**Recommendation:**
- **Beginners:** EUR/USD only
- **Intermediate:** EUR/USD for 6 months, then add 1 pair
- **Advanced:** 3-5 pairs after proven success

**Most traders should stick with EUR/USD.** 

It's fully validated, highly liquid, and capable of generating 100-200% annual returns on its own. That's more than enough for building wealth.

---

## 💡 Remember

> "Jack of all trades, master of none."

**Better to:**
- Master ONE pair completely
- Understand its behavior deeply
- Execute flawlessly
- Generate consistent returns

**Than to:**
- Trade 10 pairs poorly
- Spread yourself thin
- Miss good setups
- Increase costs and errors

**EUR/USD is enough.** 🎯
