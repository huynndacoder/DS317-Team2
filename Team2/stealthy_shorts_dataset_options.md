# Dataset Options for "Stealthy Shorts" Market Microstructure Project

## 🏆 Top Recommendation

### 1. **Hyperliquid L1 Order Flow Microstructure (10 Perps)**
**URL:** https://www.kaggle.com/datasets/marvingozo/hyperliquid-l1-order-flow-microstructure-10-perps

**Quality Score: 9.5/10** ⭐⭐⭐⭐⭐

**Why This is Perfect:**
- **6.8 BILLION rows** of order-level data (5 continuous days)
- **Maker/taker role explicitly labeled** - This is THE key feature for replicating "Stealthy Shorts"
- Wallet-level tracking - can classify trading strategies by account
- Order lifecycle: accepted, rejected, canceled, filled
- L2 order book snapshots (20 levels deep)
- 10 perpetual markets: BTC, ETH, SOL, DOGE, AAVE, LINK, PAXG, HYPE, SPX, XRP

**Key Columns for Your Project:**
```
fills.parquet:
- role: "maker" or "taker" ← CRITICAL for liquidity provider classification
- side: buy/sell
- wallet: account identifier
- price, size, fee
- is_liquidation: identify distressed trading

orders.parquet:
- order lifecycle events
- wallet-level order placement patterns

book.parquet:
- 20-level depth
- order book imbalance (OBI)
```

**Project Implementation:**
1. **Binary Classification:** Classify wallets as liquidity providers (makers) vs liquidity takers
2. **Multi-class:** Segment into informed makers, uninformed makers, aggressive takers, etc.
3. **Feature Engineering:**
   - Maker/taker ratio per wallet
   - Order cancellation rate
   - Limit order placement distance from mid
   - Fill execution quality
   - Adverse selection metrics

**Size:** 80.62 GB compressed (manageable with Parquet + sampling strategies)

---

## 🥈 Strong Alternatives

### 2. **Synthetic Limit Order Book - Market Microstructure**
**URL:** https://www.kaggle.com/datasets/sergionefedov/synthetic-limit-order-book-market-microstructure

**Quality Score: 8.5/10** ⭐⭐⭐⭐

**Why This Works:**
- 10 days of continuous LOB data
- 3 market regimes (normal, volatile, quiet)
- 2.8M order events with explicit order types
- 10-level bid/ask depth
- **Includes market impact measurements** at 10s/30s/60s horizons

**Files:**
- `lob_snapshots.csv` - 23,400 snapshots every 10 seconds
- `order_flow.csv` - 2.2M order events (submit/cancel/market)
- `trades.csv` - 600K executed trades with **aggressor side labeled**
- `market_impact.csv` - price impact vs order size

**Perfect For:**
- Learning project (synthetic = clean, no noise)
- Clear ground truth for order types
- Can classify aggressive vs passive orders
- Regime-dependent strategy classification

**Size:** ~5 files, manageable size

---

### 3. **High Frequency Crypto Limit Order Book Data**
**URL:** https://www.kaggle.com/datasets/martinsn/high-frequency-crypto-limit-order-book-data

**Quality Score: 7.5/10** ⭐⭐⭐⭐

**Why This Works:**
- 12 days of data for BTC, ETH, ADA
- 1-second, 1-minute, 5-minute frequencies
- 15 levels of order book depth
- **Order flow breakdown:** market orders, limit orders, cancellations per level

**Key Features:**
```
- bids_market_notional_x: volume of market orders at bid level x
- bids_limit_notional_x: volume of limit orders (liquidity provision)
- bids_cancel_notional_x: volume of canceled orders
- (same for asks)
```

**Project Angle:**
- Classify market participants by their limit/market order ratio
- Identify "stealthy" liquidity providers who cancel aggressively
- Detect informed traders via order flow imbalance

**Size:** Moderate, multiple frequency options

---

## 🥉 Other Solid Options

### 4. **CFM Capital Fund Management Challenge Dataset**
**URL:** https://challengedata.ens.fr/challenges/146

**Quality Score: 8/10** ⭐⭐⭐⭐

**Why This is Interesting:**
- **Real-world** tick-by-tick order book data from 24 stocks
- Level 3 (Market-by-Order) data with unique order IDs
- Track individual order lifecycle
- 100 sequential observations × 20 per stock × 504 days × 24 stocks = 24.2M rows

**Columns:**
- venue, action (A/D/U), order_id, side, price, bid, ask
- bid_size, ask_size, flux, trade (execution flag)

**Challenge:**
- Original task: classify which stock from order flow patterns
- **Your adaptation:** Classify trading strategies instead
- Can identify market makers, informed traders, noise traders from order patterns

---

### 5. **Quantitative Stock Market Dataset (Moscow Exchange)**
**URL:** https://www.kaggle.com/datasets/kkhubiev/quantitative-stock-market-dataset

**Quality Score: 7/10** ⭐⭐⭐

**Coverage:**
- 260 companies, 2022-07-01 to 2025-01-01
- Candlesticks, trades, order statistics, **order book snapshots**

**Note:** Less detailed than Hyperliquid but covers traditional equities

---

## 📊 Comparison Matrix

| Dataset | Maker/Taker Labels | Order-Level Data | Size | Real/Synthetic | Ease of Use |
|---------|-------------------|------------------|------|----------------|-------------|
| **Hyperliquid** | ✅ Explicit | ✅ 6.8B rows | 80GB | Real (crypto) | ⭐⭐⭐⭐ |
| **Synthetic LOB** | ✅ Inferred | ✅ 2.8M events | Small | Synthetic | ⭐⭐⭐⭐⭐ |
| **HF Crypto LOB** | ✅ By volume type | ✅ Per-level | Medium | Real (crypto) | ⭐⭐⭐⭐ |
| **CFM Challenge** | ❌ Must infer | ✅ Order lifecycle | Large | Real (stocks) | ⭐⭐⭐ |
| **Moscow Exchange** | ❌ Limited | ⚠️ Snapshots only | Large | Real (stocks) | ⭐⭐⭐ |

---

## 🎯 Recommended Project Approach

### **Phase 1: Proof of Concept (Use Synthetic LOB)**
- Clean data, clear labels
- Build baseline classification models
- Validate methodology

### **Phase 2: Real Data (Use Hyperliquid)**
- 6.8B rows with explicit maker/taker labels
- Wallet-level strategy classification
- Rich feature space

---

## 🔬 Specific Project Ideas with Hyperliquid Data

### **Core Research Question (from "Stealthy Shorts" paper):**
"Can we classify informed traders based on whether they provide or demand liquidity?"

### **Hypotheses to Test:**
1. **H1:** Informed short sellers place limit orders (provide liquidity) rather than market orders
2. **H2:** Wallet-level maker/taker ratio predicts profitability
3. **H3:** Order placement strategy (distance from mid-price) distinguishes informed vs uninformed

### **Classification Tasks:**

#### **Binary Classification:**
- **Target:** Profitable vs Unprofitable wallets
- **Features:** 
  - Maker/taker fill ratio
  - Average order distance from mid-price
  - Order cancellation rate
  - Fill speed (time from order to fill)
  - Order book imbalance at placement time

#### **Multi-class Classification:**
- **Classes:**
  1. Market Makers (high maker ratio, tight spreads, frequent cancels)
  2. Informed Liquidity Providers (makers with positive PnL)
  3. Aggressive Takers (low maker ratio, large sizes)
  4. Noise Traders (random patterns)

#### **Sequence Classification (Advanced):**
- Use order sequences per wallet
- LSTM/Transformer to classify trading strategy
- Input: sequence of (action, side, size, distance_from_mid, book_imbalance)
- Output: trader type

### **Feature Engineering:**

```python
# Per-wallet features
- maker_ratio = fills_as_maker / total_fills
- avg_spread_capture = avg(fill_price - mid_price)
- order_cancel_rate = cancels / total_orders
- avg_order_lifetime = avg(fill_time - order_time)
- order_size_percentile = percentile(size, market_sizes)
- adverse_selection = price_move_after_fill
- pnl_realized = sum(position * price_change)

# Order-level features
- distance_from_mid = (order_price - mid_price) / mid_price
- book_imbalance_at_placement = (bid_depth - ask_depth) / (bid_depth + ask_depth)
- order_aggressiveness = is_marketable_limit_order
- queue_position (if reconstructable)
```

### **Evaluation Metrics:**
- Classification accuracy
- Precision/Recall for "informed liquidity provider" class
- Feature importance (which signals matter most?)
- Compare maker vs taker profitability by strategy class

---

## 📦 Data Handling Tips

### **For Hyperliquid (80GB):**
```python
import polars as pl  # Much faster than pandas for large data

# Lazy loading - only read what you need
fills = pl.scan_parquet("fills_*.parquet")

# Filter and aggregate
wallet_features = (
    fills
    .filter(pl.col("coin") == "BTC")  # Start with one asset
    .group_by("wallet")
    .agg([
        (pl.col("role") == "maker").mean().alias("maker_ratio"),
        pl.col("size").sum().alias("total_volume"),
        pl.col("fee").sum().alias("total_fees")
    ])
    .collect()  # Only compute when ready
)
```

### **Sampling Strategy:**
- Don't use all 6.8B rows initially
- Sample: 1 day × 1 asset (BTC) ≈ 1.4B rows → still huge
- Further sample: Random 1% of wallets → manageable
- Scale up after proving methodology

---

## 🎓 Academic Alignment

Your project would replicate the key insight from Goyal et al. (2025):

> **Original Paper:** "Informed short sellers act as liquidity providers (limit orders) rather than liquidity demanders (market orders)"

**Your Project:** "Using order-level data with explicit maker/taker labels, classify traders by liquidity provision strategy and test whether informed traders prefer limit orders"

**Data Mining Techniques:**
✅ Binary/Multi-class classification  
✅ Feature engineering from order flow  
✅ Imbalanced learning (informed traders are rare)  
✅ Time-series analysis  
✅ Clustering (unsupervised strategy discovery)  

**Novelty:**
- Crypto perpetuals instead of equities
- Wallet-level tracking (vs anonymous in stocks)
- Explicit maker/taker labels (vs inferred)
- Can validate "stealthy shorts" hypothesis in new market

---

## 🚀 Getting Started

1. **Download Hyperliquid sample:** https://www.kaggle.com/datasets/marvingozo/hyperliquid-l1-order-flow-microstructure-10-perps
2. **Start with `fills.parquet`** - smallest file (0.21 GB) but has the key `role` column
3. **Focus on BTC first** - most liquid, cleanest data
4. **Build wallet profiles** over 1 day
5. **Label wallets** by profitability or maker/taker dominance
6. **Train classifiers** to predict labels from order flow features
7. **Validate** on remaining 4 days

---

## ⚠️ Important Notes

### **Short Interest Data vs Order Flow:**
The "Stealthy Shorts" paper analyzed **short selling** specifically. The datasets above provide **general order flow** data. 

**To adapt:**
- In crypto perpetuals, "short" = sell-side position
- Focus on **sell-side liquidity provision** specifically
- Compare sell-side limit orders vs buy-side limit orders
- Or generalize to "informed traders provide liquidity" (not just shorts)

### **Data Access:**
- All datasets listed are **publicly available** on Kaggle
- No special permissions needed
- Free to download and use for academic projects

---

## 📚 Additional Resources

**For deeper understanding:**
1. **Hyperliquid documentation:** Understanding on-chain perpetuals
2. **Market microstructure textbook:** Hasbrouck (2007) for theory
3. **Original paper:** Goyal et al. (2025) for methodology inspiration

**Code examples:**
- GitHub search: "limit order book classification"
- Kaggle kernels on the Hyperliquid dataset
- Look for "market maker detection" projects

