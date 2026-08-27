---
type: hypothesis
id: hypothesis-0001
status: untested
created_at: '2026-08-27T10:54:48.851779+00:00'
updated_at: '2026-08-27T10:54:48.851779+00:00'
topics:
- market-microstructure
- market-feedback
- price-impact
- systematic-trading
- market-participant-behavior
source_engine: chatgpt-task
---

# Hyperliquidでも、

## Hypothesis

Hyperliquidでも、
公開されたposition / OI / liquidation / funding等から
機械的売買gainのproxyを構築できれば、
cross-market feedbackを推定できる可能性がある。

## Mechanism

例:

Spot price movement
→ leveraged / hedged participant action
→ HL Perp order flow
→ HL price displacement
→ subsequent reversal

というfeedback pathを推定する。

## Supporting Evidence

このHyperliquidへの応用自体は論文には記載されていない。
本論文のidentification frameworkから導いたInference。

## Supporting Papers

- [[2608.25844]]

## Required Data

- spot return
- HL perp return
- OI
- funding
- liquidation
- aggressor flow
- order book
- participant exposure proxy
- market-hours indicator
- cross-venue prices

## Proposed Test

既知または高精度にproxy化できるparticipant gainをγ_tとして、

return_i,t+1
~ return_j,t × γ_j,t

に類するinteractionを推定し、
gain variationが大きい期間ほど
cross-market responseが強まるか検証する。

## Results

未検証。

## Status

untested
