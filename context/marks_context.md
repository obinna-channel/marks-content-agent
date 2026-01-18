# Marks Exchange Context

Use this context when generating content for Marks Exchange social media.

---

## What is Marks?

Marks is a perpetual futures trading platform for stablecoin FX markets. It enables trading USDT price movements against local currencies with leverage - essentially letting anyone trade the "real price of USD" in emerging markets.

---

## The Problem We Solve

Stablecoins already trade 24/7 and reflect the real price of the dollar across emerging markets like Argentina, Nigeria, and Bolivia. Millions of people use stablecoins as their actual FX mechanism. Yet these markets remain fragmented across P2P platforms, informal OTC networks, and country-specific channels.

There's no straightforward way to trade these price movements directly with unified liquidity.

---

## Our Solution

Marks consolidates scattered stablecoin FX markets into a single on-chain derivatives venue. Traders can long or short the value of 1 USDT against local currencies with:
- Transparent pricing
- Real liquidity
- 24/7 execution
- No banking intermediaries or capital controls

---

## Live Markets

| Pair | Description | Max Leverage | Min Collateral | Liquidation Fee |
|------|-------------|--------------|----------------|-----------------|
| USDT/ARS | Argentine Peso | 20x | 1% | 0.3% |
| USDT/NGN | Nigerian Naira | 20x | 1% | 0.3% |

## Coming Soon

- USDT/COP (Colombian Peso)
- USDT/INR (Indian Rupee)
- USDT/PKR (Pakistani Rupee)
- USDT/BOB (Bolivian Boliviano)
- USDT/KES (Kenyan Shilling)
- USDT/EGP (Egyptian Pound)

---

## How Trading Works

### Core Mechanics
- **Perpetual contracts**: No expiration dates, trade 24/7
- **USDT settlement**: All profits/losses settled in USDT
- **Pool-based liquidity**: Trades execute against liquidity pools, not individual counterparties
- **Isolated margin**: Each position has its own collateral and risk - one position's issues don't affect others

### Order Types

**Market Order** - Executes immediately at the best available price.

**Limit Order** - Lets you choose the exact price. Only fills if market reaches your price or better.

**Stop Order** - Triggers when market reaches your stop price, then executes as market order.

**Take Profit (TP)** - Closes part or all of position when market reaches your target profit level.

**Stop Loss (SL)** - Closes part or all of position when market hits your protection level.

All orders are Good-Til-Cancelled (GTC) - remain active until filled or manually cancelled.

---

## Price Feeds

Marks price feeds reflect how 1 USDT trades in each local market with continuous updates tracking stablecoin activity.

Each market draws from multiple off-chain and on-chain sources that capture real trading activity in stablecoin FX markets.

### Protections
- **Multi-source aggregation** - Prevents over-reliance on any single venue
- **Volatility controls** - Smoothing mechanisms block sudden, irregular price movements
- **Stability guardrails** - Maintains feed stability even during extreme volatility

---

## Carry (Funding + Borrowing)

**Carry = Funding fees + Borrowing fees**

Carry represents the ongoing cost (or income) from holding a leveraged position.

### Funding Fees
- Balance long vs short positioning
- Longs pay shorts when longs dominate (and vice versa)
- When balanced, funding approaches zero
- Fees are exchanged directly between traders

**Current funding rates:**
- USDT/ARS: 96% per year
- USDT/NGN: 48% per year

### Borrowing Fees
- Cost of using pool liquidity for leverage
- Scales with pool utilization (low utilization = low fees)
- Zero positions = zero fees

**Current borrowing rates:**
- USDT/ARS: 15.8% per year
- USDT/NGN: 15.8% per year

**Key insight:** Since borrowing fees are always costs while funding can be positive or negative, carry can be negative or positive depending on market conditions.

---

## Price Impact

Price impact adjusts execution prices based on how trades affect market balance.

- **Trades that reduce imbalance** get better prices
- **Trades that increase imbalance** get worse prices

Example: Opening a long when longs already dominate = worse pricing. Opening a short when longs dominate = better pricing.

Uses a non-linear curve - small imbalances create small impacts, large imbalances create disproportionately higher impact. This creates a self-balancing system.

---

## Margin & Leverage

- **Isolated margin system**: Each trade has its own dedicated collateral and risk
- **Leverage selection**: Choose your leverage when opening - higher leverage = less collateral required
- **Dynamic monitoring**: As markets move, unrealized PnL adjusts margin health
- Positions become liquidation-eligible when margin falls below safe thresholds

---

## Liquidations

Liquidation is forced closure when a position no longer has enough collateral to meet margin requirements.

**When it occurs:**
Remaining Collateral = Collateral + PnL − Fees (including accrued carry)

When remaining collateral drops below minimum requirement (1% for current markets), position is liquidated.

**What happens:**
1. Entire position closes (no partial liquidations)
2. All outstanding fees deducted (closing, borrowing, funding, liquidation fees)
3. Any remaining collateral returns to trader
4. If insolvent (collateral doesn't cover fees), trader receives nothing

**Risk mitigation:**
- Use lower leverage for larger collateral buffers
- Monitor positions during volatility
- Add collateral proactively
- Set stop-losses before liquidation thresholds

---

## Current Status

Marks is in **gated alpha release**. Trading is live but access is limited as the platform gradually onboards users.

**Access priority:**
1. Users active on demo trading platform (September 2025)
2. Additional users onboarded first-come, first-served
3. Maximum leverage and open interest caps set conservatively during alpha

**Getting access:** Join waitlist at https://form.typeform.com/to/VYGz7wjy

**Start trading:** https://app.marks.exchange/

---

## Official Channels

- **Twitter/X:** https://x.com/usemarks
- **Telegram:** https://t.me/c/usemarks/1
- **WhatsApp:** https://wa.me/13233999346

---

## Target Audience

- Traders in emerging markets seeking USD exposure
- Crypto traders familiar with perps wanting EM FX exposure
- Anyone looking to hedge or speculate on stablecoin/local currency movements
- People in countries with capital controls or limited banking access

---

## Brand Voice Guidelines

- **Knowledgeable but accessible**: Explain complex concepts simply
- **Global perspective**: We serve traders worldwide, especially in emerging markets
- **Data-driven**: Reference real market movements, rates, and metrics when available
- **Not hype-driven**: Avoid empty promises or moon talk
- **Practical**: Focus on how Marks helps traders achieve their goals
- **Empathetic to EM traders**: Understand the real challenges of currency volatility, capital controls, and limited access

---

## Key Terms

- **Perps/Perpetuals**: Perpetual futures contracts with no expiration
- **Carry**: The ongoing cost or income from holding a leveraged position (funding + borrowing fees)
- **Funding rate**: Payment between longs and shorts based on market imbalance
- **Borrowing fee**: Cost of using pool liquidity for leverage
- **Isolated margin**: Each position's collateral is separate from others
- **Pool liquidity**: Liquidity provided by LPs that traders execute against
- **Price impact**: Execution price adjustment based on how trade affects market balance
- **Liquidation**: Forced position closure when collateral falls below minimum requirement

---

## Vision

Marks is building a unified derivatives layer for global currency and stablecoin-driven markets - accessible to anyone, anywhere. Stablecoin FX is just the beginning.
