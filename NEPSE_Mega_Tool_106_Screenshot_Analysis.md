# NEPSE Mega Tool — 106-Screenshot Reverse-Engineering Report

**Source:** `PHOTOS.zip`, 106 PNG screenshots. **Method:** filenames/dimensions verified; OCR applied where available; contact sheets and full-resolution samples visually reviewed. OCR can be noisy on dense dashboards; uncertain details are marked rather than invented.

## Executive overview

The screenshot collection spans a dark-themed Nepse Alpha/SastoShare-style analytics interface. The visual sample shows a NEPSE candlestick chart with volume, market/sector dashboard cards and charts, P/E range distributions, structured fundamental tables, growth summaries, financial-comparison screens, stock-idea framework cards, and a fundamental map/scatter visualization. The left navigation appears persistent across many screens, suggesting a multi-module application rather than a single chart page. Individual records below preserve the screenshot filename and OCR evidence.

- **Charting:** Candlestick price series, volume histogram, chart toolbars/drawing controls, timeframe and chart navigation.
- **Market overview:** Market/sector cards, compact charts, sector/market tables, color-coded comparisons.
- **Valuation distribution:** Stock counts grouped into P/E ratio ranges, represented in bars and tables.
- **Fundamentals:** Company financial metric tables, growth tables, financial comparisons, valuation-related panels.
- **Stock ideas:** Preset cards labelled MultiBagger, Peter Lynch, CANSLIM, Magic Formula, F-Score, Z-Score Model, G-Score, Bargain and others visible in a screenshot.
- **Comparative maps:** Bubble/scatter map paired with price-chart view.
- **Strategy and portfolio modules:** Present as navigation or screen families in the collection; exact contents must be verified per screenshot where OCR/visuals are ambiguous.

## Design implications for NEPSE

Build a consistent security universe and data-provenance layer beneath every module. Tables should expose units, reporting period, source, update time and missing-data state. Charts should label axes and timeframes; histograms should state bin definitions; scatter/bubble plots should label both axes and bubble encoding; strategy reports should expose benchmark, fees/slippage, sample size, and out-of-sample separation where applicable. These are recommendations for the Mega Tool, not assertions about unseen controls in the screenshots.

## Screenshot-by-screenshot analysis

### 001. `Screenshot 2026-10-16 at 2.24.59 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** /&é Nepse X | Ask Gemini | 23 nepsealpha.com/nepse-chart | arty ff) @ | e Getting Started & Google [4 New Folder (ft) Home [4 Imported From Fir. | @ Customize Links [5 Imported FromiE @ -html 8 views 99.2 million | @ Free Online Games _[fJ Coordinate Geome | Q NEPSE | 4g) Indicator | Tit | 14] | 0= Footprint | = Unadj | OD of | @ Floorsheet | Q & | Ea. | @ NEPAL STOCK EXCHANGE - 1D - index (nepsealpha.com) © 02621.41 H2630.57 L2615.71 C2625.93 +4.67 (+0.18%) | Volume 4.717B | 3000.00 | 2960.00 | 2920.00
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 002. `Screenshot 2026-10-16 at 2.26.20 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Home Page SastoShare V1.1 Nepse Alpha | go s | Nepse Alpha | MARKET | Defensive Sectors | NEPSE | NEPAL STOCK EXCHANGE | Barometer | Sentiment | PORTFOLIOS | Turnover | 82.62 Cr. | Stocks near 52-Week High | Commercial Banks | 1,939.88~ | 3.14% | 7.33% | 2.09% | fe) | 77 lla | Non Life Insurance | Stocks near 52-Week Low
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 003. `Screenshot 2026-10-16 at 2.26.41 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Home Page SastoShare V1.1 Nepse Alpha | go s | Nepse Alpha | MARKET | CV" | PORTFOLIOS | w ’ | Quant Model Portfolio: | Gainers | Value | Growth Momentum HighCap MidCap SmallCap | Loosers | All | © Alpha30 | eS intr) core ____riee _vvioe__ rence. net. | © Sector Rotation | 970.00 | 1.57% | 137.00 | 21.84% | 24.21 Cr. | 80.70 Cr.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 004. `Screenshot 2026-10-16 at 2.26.45 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** go s | Page SastoShare V1.1 Nepse Alpha | Me Home | 19) | @ nepsealpha.com/sastoshare/home | AZEN | BNT | SLBSL | re {e | SIFC | 319.80 | 0.06' | 13,817.00 | 52.92 | 143.17 Cr | 306.58 Cr | MARKET | SDLBSL | 995.00 | 1.00% | 225.00 | 19.60 %
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 005. `Screenshot 2026-10-16 at 2.26.48 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Home Page SastoShare V1.1 Nepse Alpha | go s | Nepse Alpha | MARKET | Number of Stocks in PE Ratio Ranges | Number of Stocks in PB Ratio Ranges | PORTFOLIOS | Sector | 0-15 15-30 3050 50-75 75-100 | >100 | seh GO AGS (2 20) 902 rss | Commercial Banks | Quant Model Portfolios | Development Banks | © Alpha 30 | Finance | © Sector Rotation | Hotels | ANALYSIS | Hydro Power | l= Stock Analysis | Investment
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 006. `Screenshot 2026-10-16 at 2.26.53 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Home Page SastoShare V1.1 Nepse Alpha | go s | Nepse Alpha | Non Life Insurance | MARKET | Others | Tradings | PORTFOLIOS | Percentage of stocks above Moving Average | Quant Model Portfolios | Sector | Above 10 SMA | Above 20 SMA | Above 50 SMA | Above 200 SMA | Above 50_200 SMA | © Alpha 30 | 10.53 % | Commercial Banking | © Sector Rotation | Trading | ANALYSIS
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 007. `Screenshot 2026-10-16 at 2.27.57 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** one | @ nep | * Al | @ Sastoshare | MARKET | Overview | @ Home | B News Letter | Symbol: ADBL | - Agricultural Development Bank Limited | Nepse Alpha Quant Ranking | PORTFOLIOS | Sector: Commercial Banks | @ Alpha Folio | Momentum | S Quant Model Portfolios | iy Me | Jan 9th 2022 319.8” (-0.37)% Volume!2342.00 | Value | © Alpha30 | Market Capitalization | NPR 42,174,954,984.24
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 008. `Screenshot 2026-10-16 at 2.28.00 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** one | mM, | ney | Ipha | * Ah | @ Sastoshare | MARKET | Overview | ACLBSL (Aarambha Chautari Laghubitta Bittiya Sanstha Limited) | @ Home | ADBL (Agricultural Development Bank Limited) | B News Letter | Symbol: ADBL | - Agricultural Development | ADBLB86 (8 Years, 4% Agriculture Bond) | PORTFOLIOS | Sector: Commercial Banks | ADBLB87 (9 years, 4% Agriculture Bond) | @ Alpha Folio | ADBLD83 (10.35% ADBL Krisi Bank Rinpatra 2083) | ey An | Jan 9th 2022 319.8” (-0.37)% Volume!2342.00
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 009. `Screenshot 2026-10-16 at 2.28.10 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Stock Analysis Sastoshare V.1.1 Nepse Alpha | go s | Nepse Alpha | at) | Size | High Cap | MARKET | Shares Outstanding | 131,879,159 Nos | B News Lette | Health (F-Score) | PORTFOLIOS | @ Alpha Folio | Low: 0 | High: 9 | 425.00 | S Quant Model Portfolios | 400.00 | © Alpha30 | 375.00 | Fundamental Growth (G-Score) | © Sector Rotation
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 010. `Screenshot 2026-10-16 at 2.28.23 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** @ nepsealpha.com | 350.00 | @ Sastoshare | Low: 0 | High: 8 | MARKET | 300.00 | @ Home | 275.00 | B News Letter | Bankruptcy Risk (Z-Score) | Jun | Jul | PORTFOLIOS | May | @ Alpha Folio | Symbol FiscalYear QoQGrowth | YoY Growth | Margin TT™ | BookValue EPSt™ ROETTM | PET™™ PB | PStm™ LTP
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 011. `Screenshot 2026-10-16 at 2.28.28 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Nepse | @ nepsealpha.com | ¢ A | * Alpha : | Share Registrar | NIBL Ace Capital Limited | @ Sastoshare | Website | Agricultural Development Bank, Nepal was established in 1968 under the | https://www.adbl.gov.np/ | ADBN Act 1967. The Land Reform Savings Corporation was merged with | MARKET | Email | info@adbl.gov.np | ADBN in 1973. Subsequent amendments to the Act empowered the bank to | @ Home | Contact No. | 1-4263387, 4212975 | extend credit to small farmers under group liability and expand the scope of | B News Letter | financing to promote cottage industries. The amendments also permitted the | Head Office
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 012. `Screenshot 2026-10-16 at 2.28.40 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** one | GS, | nepsealpha.com | * Alpha | Mr. Prakas! | Aumar sanje | Uirector | Mr. Krishna Gopa | Promoter | U.UU | @ Sastoshare | Mr. Ramesh Duwadi | Director | Ms. Laxmi Shrestha | 741,890.00 | MARKET | Dr. Indira Shrestha (Maskey) | @ Home | Mr. Sanjeeb Paudel | 2,461 | B News Letter | Mr. Hari Prasad Parajuli
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 013. `Screenshot 2026-10-16 at 2.29.08 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** @ nepsealpha.com | » AR | @ Sastoshare | Fundamental Signal | Technical Signal | MARKET | @ Home | iii | B News Letter | PE tm | 17.84 | 35.04 wait | 9.63 sre | RSI14 | 42.23 | 50.25 yet | 24.78 nasi | PORTFOLIOS | @ Alpha Folio | PBV | ee) | 3.31 naBiL
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 014. `Screenshot 2026-10-16 at 2.29.33 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** @ nepsealpha.com | *» Al | @ Sastoshare | MARKET | l= Stock Analysis | #@ Home | Stock Analysis | B News Letter | ADBL (Agricultural Development Bank Limited) V | PORTFOLIOS | Overview | Financials | Growth | Ratios | Comparison | Intrinsic Value | Dupoint | Dividend | Graph | @ Alpha Folio | S Quant Model Portfolios | Audited Annual Reports
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 015. `Screenshot 2026-10-16 at 2.29.37 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** @ nepsealpha.com | Alpt | @ Sastoshare | MARKET | Stock Analysis | @ Home | B News Letter | ADBL (Agricultural Development Bank Limited) Vv | PORTFOLIOS | Overview | Financials | Growth | Ratios | Comparison | Intrinsic Value | Dupoint | Dividend | Graph | @ Alpha Folio | S Quant Model Portfolios | Growth Summary | © Alpha 30
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 016. `Screenshot 2026-10-16 at 2.29.40 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** ; Ne | pse | @ nepsealpha.com | * Alpha : | @ Sastoshare | Growth Summary | MARKET | @ Home | a ee | B News Letter | Overall Growth | 6.19 % | 9.26% | 21.71% | 10.18 % | 10.09 % | PORTFOLIOS | @ Alpha Folio | Core Growth | 9.84% | 11.00 % | 20.44%
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 017. `Screenshot 2026-10-16 at 2.29.55 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** ot) | @ nepsealpha.com | Alp Se | @ Sastoshare | Growth Summary | MARKET | @ Home | B News Letter | Overall Growth | 6.19 % | 9.26% | 21.71% | 10.18 % | 10.09 % | PORTFOLIOS | @ Alpha Folio | Core Growth | 9.84% | 11.00 % | 20.44% | 10.21% | 11.37%
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 018. `Screenshot 2026-10-16 at 2.30.19 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Neps | nepsealpha.com | * Alpfia | @ Sastoshare | MARKET | Stock Fundamental Map | NEPSE vs Commercial Banks vs ADBL | @ Home | 0.2 | Sector Average | B News Letter | Val | PORTFOLIOS | SEB) | 0.15 | PEBL | aa) (o | -5% | @ Alpha Folio | DNMB: | NBB) | “© ren
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 019. `Screenshot 2026-10-16 at 2.30.24 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** @ nepsealpha.com | * Alpha | @ Sastoshare | 0.05 | -20% | MARKET | -25% | @ Home | B News Letter | 100 | 150 | 200 | 250 | 30% | PORTFOLIOS | -35% | @ Alpha Folio | xAxis | yAxis | Size | S Quant Model Portfolios | -40%
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 020. `Screenshot 2026-10-16 at 2.30.32 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** nepsealpha.com | @ Sesto | share | vas | MARKET | Stock Analysis | @ Home | B News Letter | ADBL (Agricultural Development Bank Limited) v | PORTFOLIOS | Overview | Financials | Growth | Ratios | Comparison | Intrinsic Value | Dupoint | Dividend | Graph | @ Alpha Folio | S Quant Model Portfolios | Margin of safety
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 021. `Screenshot 2026-10-16 at 2.30.38 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Nepse | nepsealpha.com | * Alpha : | @ Sastoshare | Margin of safety | MARKET | @ Home | S.N | Valuation Models | Formula Value (NPR) | Margin of Safety (LTP: NPR 319.8) | B News Letter | Discounted Earning Methods | 172.63 | 1 By NPR.147 | PORTFOLIOS | @ Alpha Folio | Graham Number | 294.29 | NPR.26 | S Quant Model Portfolios | PEG Ratio
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 022. `Screenshot 2026-10-16 at 2.30.46 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** @ nepsealpha.com | share | Graham Number | 294.29 | 1 By NPR.26 | MARKET | PEG Ratio | 133.19 | y NPR.187 | @ Home | B News Letter | Gordon Model | 1,252.46 | PORTFOLIOS | @ Alpha Folio | S Quant Model Portfolios | Discounted Earning Methods Calculation | Current TTM EPS | 17.93 | © Alpha30 | © Sector Rotation | Growth
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 023. `Screenshot 2026-10-16 at 2.30.53 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Nepse | @ nepsealpha.com | * Alpha | @ Sastoshare | x @ | MARKET | Stock Analysis | #@ Home | B News Letter | PORTFOLIOS | Dupoint | @ Alpha Folio | SS Quant Model Portfolios | Du point ROE Analysis | © Alpha30 | The DuPont equation is breaks return on equity down into three parts: profit margin, asset turnover, and leverage (Equity Multiplier).viie ROE= Net Profit Margin * Asset Turnover * | © Sector Rotation | Equity Multiplier | ANALYSIS | l& Stock Analysis | @ Global Stock Ideas | Fiscal year and related data
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 024. `Screenshot 2026-10-16 at 2.30.59 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Nep: | nepsealpha.com | * Ah | @ Sastoshar | vas | MARKET | l& Stock Analysis | #@ Home | Stock Analysis | B News Letter | ADBL (Agricultural Development Bank Limited) v | PORTFOLIOS | Overview | Financials | Growth | Ratios | Comparison | Intrinsic Value | Dupoint | Dividend | Graph | @ Alpha Folio
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 025. `Screenshot 2026-10-16 at 2.31.12 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Ms Global Sto | Nepse | @ nepsealpha.com/sastoshare/signal-summary | Aipae | © Alpha30 | @ Global Stock Ideas | © Sector Rotation | ANALYSIS | Global Stock Ideas | l= Stock Analysis | MultiBagger | Peter Lynch | = Dividend Book | © History | © Yield Chart | Joel Greenblatt | Altman's | © Scenario Chart | Magic Formula | Z-Score Model | © Safety Check | Financially Healthy Stocks
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 026. `Screenshot 2026-10-16 at 2.31.29 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Global Sto | * Nepse | @ nepsealpha.com, | lare | sur | 2 4xA® PEP | @ Sastoshar | vat | x @ | © Alpha 30 | @ Global Stock Ideas | © Sector Rotation | ANALYSIS | Global Stock Ideas | l= Stock Analysis | < Back | Peter Lynch | Z Dividend Book | Peter Lynch investing style is based on selection of securities based on well-grounded expectation concerning firms's growth prospects | © History | © Yield Chart | © Scenario Chart
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 027. `Screenshot 2026-10-16 at 2.31.36 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Global Stock | g Nepse | summar | @ nepsealpha.com, | are/signa | 2 4A» APP | @ Sastoshare | © Alpha 30 | © Sector Rotation | rki | Cur | Quick | ANALYSIS | ALBSL | NPR 1127 | -0.27 % | 376.32 Cr | 30.45 | [= Stock Analysis | bal EPs ; i | hy, | @ Global Stock Ideas
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 028. `Screenshot 2026-10-16 at 2.31.44 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Me Global Stock Ideas | Nepse | @ nepsealpha.com/sastoshare/signal-summary | @ aStosnare | © Alpha30 | © Sector Rotation | ANALYSIS | l= Stock Analysis | @ Global Stock Ideas | Z Dividend Book | © History | NPR 463 | -0.86 % | 521.41 Cr | 25.99 | Viome, | ea re | © Yield Chart | NPR 330 | -1,93 % | 16.44 | pees
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 029. `Screenshot 2026-10-16 at 2.32.11 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** kTestin | % Al | nepsealpha | @ Sastoshare | Demand | 0 Nos | Supply | 160 Nos | All Stocks | 191 Nos | © Alpha30 | Select | ADBL(Agricultural Development Bank Limited) | © Sector Rotation | ANALYSIS | l= Stock Analysis | @ Global Stock Ideas | Signal Summary | ADBL | Symbol | Z Dividend Book | © History
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 030. `Screenshot 2026-10-16 at 2.32.32 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** menta | BackTestin | cone | gnals | My Sign | Nep: | nepsealpha.com | 400.00 | share | © Alpha 30 | "ay | 380.00 | Wl! | all | © Sector Rotation | 360.00 | ANALYSIS | aa, | l= Stock Analysis | 340.00 | @ Global Stock Ideas | 4 l | lity
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 031. `Screenshot 2026-10-16 at 2.32.58 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** nepsealpha.com | epsea | 400.00 | @ Sastoshar | vas | © Alpha30 | 380.00 | © Sector Rotation | Wt tha fl ll | ANALYSIS | 360.00 | aa, | l= Stock Analysis | 340.00 | @ Global Stock Ideas | % Dividend Book | "iy | el i Pie Tal | if 1 | a ia’ wl | ils | © History
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 032. `Screenshot 2026-10-16 at 2.33.22 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Technica | igna | und | esting | Sma | gnals | My Signals | #7 Nepse | nepsealpha.com | * Alpha | share | vas | x @ | MARKET | ulll Stock Signals > Fundamental Signals | @ Home | Selected Stock | Sector | Valuation type | Graham Number | LTP | Last Trading Day | B News Letter | PORTFOLIOS
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 033. `Screenshot 2026-10-16 at 2.33.29 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Is | Technica | ignal | ignals | Fundamental Si | k Signals | My Signals | Nepse | @ nepsealpha.com | * Alpha : | @ Sastoshare | x @ | MARKET | ulll Stock Signals > Backtesting Engine | @ Home | AKPL (Arun Kabeli Power Ltd.) | BACKTEST Q | B News Letter | PORTFOLIOS | Indicators | Parameter (days) | SMA | ee ) | @ Alpha Folio | SMA Ranges
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 034. `Screenshot 2026-10-16 at 2.33.36 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Techi | kTestin | Signals | My Signals | Nepse | nepsealpha.com | * Ak | @ Sastoshare | © Alpha30 | Performance of Indicator Trading VS Buy and Hold | If we Back test AKPL on available historical data | © Sector Rotation | using MACD indicator, the total return would be | fin Pon f om Prof Pa] | 91.87% and CAGR would be 13.28%. | ANALYSIS | l= Stock Analysis | + 150% | @ Global Stock Ideas | Z Dividend Book | arom | Disclaimer: Backtested Result is a hypothetical | © History
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 035. `Screenshot 2026-10-16 at 2.33.38 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** ace | echnical | kTestir | pse | nepsealpha.com | 60% | @ Sastoshare | © Alpha 30 | 30% | © Sector Rotation | ANALYSIS | otal | e Trade | l= Stock Analysis | alue | @ Global Stock Ideas | -30% | Total Negative Trades | Z Dividend Book | © History | © Histogram | + Trading Returns
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 036. `Screenshot 2026-10-16 at 2.33.39 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Is | Techn’ | Sigr | ital Si | kTestini | Ay Signals | Nepse | @ nepsealpha.com | * Alpha : | @ Sastoshare | © Alpha 30 | © Histogram | + Trading Returns | © Sector Rotation | ANALYSIS | [= Stock Analysis | Returns Breakdown | Performance Summary | (+) Global Stock Ideas | More than 5% Gains (Nos) | 8 Nos | Total Return of Indicator | 92%
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 037. `Screenshot 2026-10-16 at 2.33.46 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Is | Technica | ignal | Stock Signals | Fundamental Si | Nepse | @ nepsealpha.com | * Alpha : | @ Sastoshare | x @ | MARKET | ulll Stock Signals > My Signals | @ Home | B News Letter | All Signals | Buy Signal | Sell Signal | Reset Signals | PORTFOLIOS | Show 10 | entries | Search: | @ Alpha Folio | S Quant Model Portfolios
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 038. `Screenshot 2026-10-16 at 2.33.52 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** nepsealpha com. | * Al | All Signals | MARKET | My Signal * | Symbol | Sector | Edit Buy | Edit Sell | Edit buy for ADBL | PORTFOLIOS | Filter Options | act lich) | Macd Bullish | Yes | JORDI | ANALYSIS | Inv | 70°F | 7:40 AM | aE G | (<i)
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 039. `Screenshot 2026-10-16 at 2.33.58 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** nepsealpha com. | * Al | All Signals | MARKET | My Signal * | Symbol | Sector | Edit Buy | Edit Sell | Edit buy for ADBL | PORTFOLIOS | Filter Options | Macd Bullish | No rT @) Yes | JORDI | ANALYSIS | Inv | 70°F | 7:40 AM | aE G | (<i) | 5@)
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 040. `Screenshot 2026-10-16 at 2.34.10 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Néps | nepsealpha.com | > Alba | @ Sastoshar | vis | x @ | MARKET | = Dividend Book > History | #@ Home | B News Letter | Commercial Banks | i) Agricultural Development Bank Limited (ADBL) | PORTFOLIOS | @ Alpha Folio | S Quant Model Portfolios | Total Dividend | Payout Ratio | Only Bonus | Only Cash | YOY Change in dividend | Average Dividend | Growth AAGR
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 041. `Screenshot 2026-10-16 at 2.34.14 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** @ nepsealpha.com | x Al 4 | @ Sastoshare | MARKET | #@ Home | B News Letter | PORTFOLIOS | mall | 2069/2070 | 2070/2071 | 2071/2072 | 2072/2073 | 2073/2074 | 2074/2075 | 2075/2076 | 2076/2077 | 2077/2078 | 2078/2079 | @ Alpha Folio | © Sector Minimum Total Dividend | @ Sector Maximum Total Dividend -®- ADBL Total Dividend | © Sector Average Total Dividend
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 042. `Screenshot 2026-10-16 at 2.34.25 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Néps | nepsealpha.com | > Alga | @ Sastoshare | x @ | MARKET | = Dividend Book > Yield Chart | @ Home | Yield Chart | ADBL (Agricultural Development Bank Limited) | B News Letter | PORTFOLIOS | Pam Pom Pro oy J at | @ Alpha Folio | S Quant Model Portfolios | + 10% | © Alpha30 | © Sector Rotation | + 8% | ANALYSIS | + 6% | l= Stock Analysis
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 043. `Screenshot 2026-10-16 at 2.34.27 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** #7 Néps | nepsealpha.com | > Alga | @ Sastoshare | x @ | MARKET | = Dividend Book > Yield Chart | #@ Home | Yield Chart | ADBL (Agricultural Development Bank Limited) | B News Letter | PORTFOLIOS | Pam Pom Pyro y J a | @ Alpha Folio | S Quant Model Portfolios | + 0% | © Alpha30 | © Sector Rotation | + 8% | 6.62 (%) | ANALYSIS | +6'
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 044. `Screenshot 2026-10-16 at 2.34.32 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** hart | Ay Nepsé | nepsealpha.com | Alba | x @ | @ Sastoshare | MARKET | = Dividend Book > Scenario Chart | @ Home | Scenario Chart | NABIL (Nabil Bank Limited) | B News Letter | PORTFOLIOS | @ Alpha Folio | 1250% | + 200% | S Quant Model Portfolios | © Alpha 30 | + 150% | © Sector Rotation | + 750% | ANALYSIS
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 045. `Screenshot 2026-10-16 at 2.34.35 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** end B | ‘ety Check | yay Népsé | nepsealpha.com | > Alba: | x @ | @ Sastoshare | MARKET | = Dividend Book > Safety Check | #@ Home | B News Letter | Dividend Safety Checklist | ADBL (Agricultural Development Bank Limited) | PORTFOLIOS | Particulars | Value | Comments | @ Alpha Folio | S Quant Model Portfolios | Dividend to Cashflow per share | 75.92% | <75 % is considered good
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 046. `Screenshot 2026-10-16 at 2.34.44 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Dividend Book Sastoshare V.1.1 Nepse Alpha | Nepse Alpha | AARKET | denc | Dividend Safety Checklist | PORTFOLIOS | Particulars | Value | Comments | it M | Dividend to Cashflow per share | 75.92% | <75 % is considered good | © Alpha30 | @ Average 5 years Payout ratio | 61.05% | Payout ratio between 30%-60% is considered Healthy | © Sector Rotation | ANALYSIS | @ 5 years Average Dividend | 21.79% | l= Stock Analysis
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 047. `Screenshot 2026-10-16 at 2.35.02 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** <7 Nepse | nepsealpha.com | * Abo@a | @ Sastoshare | x @ | @Q Advanced Screener | © Fundamental Signals | %y Backtesting Engine | Advanced Screener | ‘D Reset | %y My Signals | RSI-14 | MACD VS Signal Line | Price > 200 SMA | 5 SMA>20SMA | Bollinger Band(20) | Stochastic 14 | Price > 20SMA | Price > SOSMA | SCREENING & COMPARISON | Any | @ Advanced Screener
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 048. `Screenshot 2026-10-16 at 2.35.10 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** ly Nepse™ | @ nepsealpha.com | * Alpifo : | @ Sastoshare | PEG | ROE | ROA | Dividend Yield | Paid Up Capital | EPS | Book Value | YOY Profit Growth Vs Sector | Any | © Fundamental Signals | Debt to Equity | Payout ratio (%) | One Year Beta | One Week Float Turnover | 3 Year Beta | 50 Day Relative Volume | Volume crossover | Relative Strength (RS)
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 049. `Screenshot 2026-10-16 at 2.35.12 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** eene | 47 Nepse | nepsealpha.com | * Alpio : | ROA | @ Sastoshare | PEG | ROE | Dividend Yield | Paid Up Capital | EPS | Book Value | YOY Profit Growth Vs Sector | Any | © Fundamental Signals | One Year Beta | One Week Float Turnover | 3 Year Beta | Volume crossover | Debt to Equity | Payout ratio (%) | 50 Day Relative Volume
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 050. `Screenshot 2026-10-16 at 2.35.16 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Fundamental data / financial comparison
- **What it represents:** The interface presents company financial metrics in structured tables, likely organized by metric and period/company. This representation is suitable for side-by-side comparison, but individual values and the precise metric list should be checked from the original image.
- **Data representation:** Structured metric table, period comparison, and/or paired plots; numerical cells are more precise than color summaries.
- **OCR evidence (best effort):** Ns Chart | Nepse | @ nepsealpha.com | Wl Chart Pattern Scan | © Fundamental Signals | %g Backtesting Engine | Chart Scanner | Sq My Signals | Bullish Channel} Bearish Channel @} | Double Top 2) | Double Bottom ® | Head and Shoulder @ | Inverse Head and Shoulder @ | Multiple top® | Multiple Bottom ia) | Broad | SCREENING & COMPARISON | Q Advanced Screener | Wi Chart Pattern isan | &% Stock Comparison | Bullish Channel | Advanced Comparison
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 051. `Screenshot 2026-10-16 at 2.35.20 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Fundamental data / financial comparison
- **What it represents:** The interface presents company financial metrics in structured tables, likely organized by metric and period/company. This representation is suitable for side-by-side comparison, but individual values and the precise metric list should be checked from the original image.
- **Data representation:** Structured metric table, period comparison, and/or paired plots; numerical cells are more precise than color summaries.
- **OCR evidence (best effort):** can | Me Chart Pattern | Nepse | @ nepsealpha.com | Wl Chart Pattern Scan | © Fundamental Signals | %g Backtesting Engine | Chart Scanner | Sg My Signals | Broad | SCREENING & COMPARISON | Bullish Channel @ Bearish Channel (2) | Double Top 2) | Double Bottom 6 | Head and Shoulder @} | Inverse Head and Shoulder @ | Multiple Ttop® | Multiple Bottom i@) | Q Advanced Screener | §] Stock Comparison | Head and Shoulder | aif
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 052. `Screenshot 2026-10-16 at 2.35.24 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** ¢ 9 | - Nepse | @ nepsealpha.com | * Alpio : | @ Sastoshare | Finance | © Fundamental Signals | General | Profitability | Health | Relative Value | Risk | Technical | Market Share | @ 15 Stocks Found | %y Backtesting Engine | Total Assets | Loans And Advances To Customers | Net Profit | Interest Income | Sy My Signals | Symbol
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 053. `Screenshot 2026-10-16 at 2.35.26 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** - Nepse | @ nepsealpha.com | *» Aio@o | @ Sastoshare | x @ | &]S stock Comparison > Growth Comparison | © Fundamental Signals | %y Backtesting Engine | Sector | Particular | %q My Signals | Commercial Banks | Total Assets | SCREENING & COMPARISON | Q Advanced Screener | Share premium | Wi Chart Pattern Scan | Loans and advances to customers | &% Stock Comparison | Subject | 3Y Cal | AAGR
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 054. `Screenshot 2026-10-16 at 2.35.28 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** npari | 47 Nepse™ | nepsealpha.com | *» Alo@a | x @ | @ Sastoshare | &] stock Comparison > Financial Comparison | © Fundamental Signals | %y Backtesting Engine | Sector | Symbols | Fiscal Year | Quarter | Sy My Signals | SCREENING & COMPARISON | Commercial Banks | Agricultural Development Bank Limited(ADB! v | 078-079 | Q Advanced Screener | Wi] Chart Pattern Scan | #Add & Compare | &% Stock Comparison
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 055. `Screenshot 2026-10-16 at 2.35.33 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** ¢ 9 | " Nepse’ | @ nepsealpha.com | * Alpio : | @ Sastoshare | x @ | &] stock Comparison > Price & Ratio's Compare | © Fundamental Signals | %g Backtesting Engine | Sector | First Date | Second Date | Price Type | %q My Signals | Commercial Banks | & 2022-08-11 | & 2022-09-11 | Adjusted | SCREENING & COMPARISON | Q Advanced Screener | Wl] Chart Pattern Scan | &% Stock Comparison
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 056. `Screenshot 2026-10-16 at 2.35.36 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** ly Nepse™ | nepse | alpha.com, | * Abo@a | @ Sastoshar | vas | x @ | &% Stock Comparison > Chart Compare | © Fundamental Signals | %y Backtesting Engine | Sector | Particular | %y My Signals | Commercial Banks | Book ValueWis.) | SCREENING & COMPARISON | Base Rate in % | Q Advanced Screener | Symbols | k Vatue(Rs | Wil Chart Pattern Scan | Agricutural Development Bank Limited (ADBL)_*Jf Nabil Bank Limited (NABIL) Jf Bank of Kathmandu Ltd. (BOKL) J
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 057. `Screenshot 2026-10-16 at 2.36.02 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** nepsealpha.com | My Portfolio | lad. My Performance | & Portfolio Analyst | 6&8 My Stock Info | ™ Trader Analytics | & Optimization | BF Corporate Action | @ Sastoshare | MARKET | 323 By Stocks | #@ Home | Samplel | B News Letter | PORTFOLIOS | @ Alpha Folio | S Quant Model Portfolios | 63.66% NPR 22,356,615.00 | NPR 0.00 | © Alpha 30 | AS OF 2022-09-08 | © Sector Rotation
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 058. `Screenshot 2026-10-16 at 2.36.07 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** im) | ine | @ nepsealpha.com, | @ Sastoshare | Total Charges | MARKET | @ Home | NPR. 75.00 | NPR. 0.00 | NPR. 97,500.00 | NPR. 5,250.00 | NPR. 102,825.00 | B News Letter | PORTFOLIOS | @ Alpha Folio | Gs---+ | SS Quant Model Portfolios | My Portfolio | © Alpha 30 | Current Portfolio | Cash Divtdend | © Sector Rotation
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 059. `Screenshot 2026-10-16 at 2.36.10 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** nepsealpha.com | x @ | @ Sastoshare | MARKET | @ Alpha Folio | @ Home | My Portfolio | lu My Performance | & Portfolio Analyst | 68 My Stock Info | “ Trader Analytics | & Optimization | Bi Corporate Action | B News Letter | der | 823 By Stocks | PORTFOLIOS | Samplel | S Quant Model Portfolios | © Alpha30 | © Sector Rotation | ANALYSIS
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 060. `Screenshot 2026-10-16 at 2.36.13 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** mM, | ney | ealph | t%4 | @ Sastoshare | Samplel | MARKET | #@ Home | B News Letter | PORTFOLIOS | 63.66% NPR 22,356,615.00 | NPR 0.00 | @ Alpha Folio | S Quant Model Portfolios | © Alpha 30 | -15.09 | 7.84 | 51% | 1.16 | 0.88 | 1.62 | © Sector Rotation
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 061. `Screenshot 2026-10-16 at 2.36.17 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** im) | iepos | @ nepsealpha.com, | ra’ | @ Sastoshare | Total Charges | MARKET | #@ Home | NPR. 75.00 | NPR. 0.00 | NPR. 97,500.00 | NPR. 5,250.00 | NPR, 102,825.00 | B News Letter | PORTFOLIOS | @ Alpha Folio | [ison + | en | S Quant Model Portfolios | My Portfolio | © Alpha 30 | Current Portfolio | Cash Dividend
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 062. `Screenshot 2026-10-16 at 2.36.22 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** nepsealpha.com | bind | My Portfolio | lu. My Performance | & Portfolio Analyst | 6% My Stock Info | “™ Trader Analytics | & Optimization | BF Corporate Action | @ Sastoshare | MARKET | 323 By Stocks | #@ Home | Samplel | B News Letter | PORTFOLIOS | @ Alpha Folio | S Quant Model Portfolios | 63.66% NPR 22,356,615.00 | NPR 0.00 | © Alpha30 | AS OF 2022-09-08
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 063. `Screenshot 2026-10-16 at 2.36.26 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** @ nepsealpha.com | @ Sastoshare | Total Charges | MARKET | ee ee ee a | #@ Home | NPR. 75.00 | NPR. 0.00 | NPR. 97,500.00 | NPR. 5,250.00 | NPR. 102,825.00 | B News Letter | PORTFOLIOS | @ Alpha Folio | [iisoo-+ | s+ | S Quant Model Portfolios | My Portfolio | © Alpha 30 | Current Portfolio | Cash Dividend | © Sector Rotation | Buy History
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 064. `Screenshot 2026-10-16 at 2.36.29 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** nepsealpha.com | @ Sastoshare | MARKET | Total Charges | #@ Home | B News Letter | Ee ee ee | NPR. 97,500.00 | NPR. 5,250.00 | NPR. 75.00 | NPR. 0.00 | NPR. 102,825.00 | PORTFOLIOS | @ Alpha Folio | S Quant Model Portfolios | iso + | + | © Alpha 30 | My Portfolio | © Sector Rotation | ANALYSIS | Current Portfolio | Buy History
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 065. `Screenshot 2026-10-16 at 2.36.31 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Alpha Fol | nepsealpha.com | epse | alata | @ Sastoshare | MARKET | @ Alpha Folio | #@ Home | My Portfolio | lil My Performance | & Portfolio Analyst | 6% My Stock Info | ™ Trader Analytics | & Optimization | Bi Corporate Action | B News Letter | PORTFOLIOS | Time-weighted return performance which automatically adjusts returns for the impact of|cash flows and outflows over time. | Portfolio Performance Stock | S Quant Model Portfolios | Current Quarter | Two Quarters Back
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 066. `Screenshot 2026-10-16 at 2.36.34 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** epse | nepsealpha.com | alata | x @ | @ Sastoshare | MARKET | @ Alpha Folio | #@ Home | B News Letter | f My Portfolio | ll My Performance | & Portfolio Analyst | 6% My Stock Info | ™ Trader Analytics | & Optimization | BF Corporate Action | PORTFOLIOS | Technical Info | Fundamental Info | Symbol | 200 SMA | SS Quant Model Portfolios
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 067. `Screenshot 2026-10-16 at 2.36.35 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Alpha Folio Sastoshare V.1.1 Nepse Alpha | go s | Nepse Alpha | MARKET | f# My Portfolio | [ul My Performance | && Portfolio Analyst | &8 My Stock Info | “ Trader Analytics | a Optimization | a Corporate Action | PORTFOLIOS | Auto Analysis of My Portfolio ® | @ Alpha Folio | Quant Model Portfolio: | Portfolio Analyst Disclaimer: This is auto-generated Report. Investors are not advised to act based on this report. This analysis simply shows the status of portfolio based on the | stock holdings entered in Alpha Folio by its users and the data available within Nepsealpha Website. Nepsealpha pvt ltd does not guarantee the correctness and completeness of | © Alpha 30 | the data. Information may get changed or updated at any time without notification of changes to users. The results are based on the stock holdings and their respective weight in | the portfolio. The Parameters are generally followed guidelines by the investors all around the world. They should not be treated as standard format. Nepse Alpha Pvt Ltd is not | © Sector Rotation | liable for any kind of loss occurred based on the action of investors following this report.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 068. `Screenshot 2026-10-16 at 2.36.39 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** @ nepsealpha.com, | epse | alata | @ Sastoshare | Risk Reward Status of my positions | MARKET | #@ Home | Filter Type | Symbol | B News Letter | Daily Chart | © 2022-09-08 14:59:00 | PORTFOLIOS | @ Alpha Folio | SS Quant Model Portfolios | LTP (NRP) | Support | Resistance | Risk Reward Ratio | Risk Reward (%) | Comment | © Alpha30
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 069. `Screenshot 2026-10-16 at 2.36.50 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** im) | @ nepsealph | > Alpba: | @ Sastoshare | At the ground of everything, Nepsealpha do is dedicated research and sharing sensible to practical investing ideas and findings with Nepalese investors which may ultimately give | MARKET | investors a trading or investing advantage. The performance returns of the overall Alpha 30 Stocks that appear in the Model Portfolio (Alpha 30 Stocks) are computed daily (plus any | dividends and right share or any other form received). An equally-weighted average return of all top 20 Stocks from Alpha 30 stocks is calculated daily to track the performance of a | #@ Home | group of Alpha 30 Stocks. The daily returns are then compounded to arrive at the total return. During some volatile periods, the portfolio exposure may be reduced partially which is | B News Letter | discussed in the newsletter from time to time. For certain Stocks for which no price was available during a certain time, the return will be calculated as zero. Some or all Stocks may | PORTFOLIOS | change weekly at maximum as identified by the bullish stock algorithm. | @ Alpha Folio | S Quant Model Portfolios | folios | turns | © Alpha 30 | NEPSE | 136.32 % | 10.40 %
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 070. `Screenshot 2026-10-16 at 2.36.59 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** All | nepsealpha.com | group of Alpha 30 Stocks. The daily returns are then compounded to ie at the total return. During some volatile periods, the portfolio exposure may be reduced partially which is | @ Sastoshare | discussed in the newsletter from time to time. For certain Stocks for which no price was available during a certain time, the return will be calculated as zero. Some or all Stocks may | MARKET | change weekly at maximum as identified by the bullish stock algorithm. | @ Home | B News Letter | CAGR | PORTFOLIOS | NEPSE | 136.32 % | 10.40 % | @ Alpha Folio | 41.84% | Alpha 30 Stocks | 1,989.95 % | S Quant Model Portfolios | © Alpha30 | Overall Performance | Running Quarter
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 071. `Screenshot 2026-10-16 at 2.37.03 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** nepsealpha.cor | Népsé | @ nepsealpha.com | > Alba | CLBSL | NPR 878.9 | 1.15% | 253.23 Cr | 34.39 | @ Sastoshare | EBL | NPR 487.2 | 0.04 % | 4,612.49 Cr | 18.12 | nen | MARKET | Shleg | #@ Home | Sens | B News Letter | FMDBL
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 072. `Screenshot 2026-10-16 at 2.37.06 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** im) | cai | nepsealpha.com | > Alpha | x @ | @ Sastoshare | MARKET | © Quant Model Portfolios > Sector Rotation | @ Home | B News Letter | Or h | Sector Price Status | Sector Volume Status | Last 12 Months Sector Returns | PORTFOLIOS | on Stocks | @ Alpha Folio | Stocks Sector | S Quant Model Portfolios | BNT | Manufacturing And | + 10%
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 073. `Screenshot 2026-10-16 at 2.37.09 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** Model Protfolio Sastoshare V.1.1 Nepse Alpha | go s | Nepse Alpha | Pes | MARKET | Quant Model Portfolios | ectc | Rotatio: | Sector Price Status | Last 12 Months Sector Returns | Top Sector Rotation Stocks | Sector Volume Status | PORTFOLIOS | Sector * | 1Day | 1 Week | 1 Month | @ Alpha Folio | BANKING | 15.12Cr 3 | 71.50Cr 2 | 328.67Cr 3
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 074. `Screenshot 2026-10-16 at 2.37.13 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** @ nepsealpha.com | 28) | @ Sastoshare | x @ | MARKET | & Quant Model Portfolios > Sector Rotation | @ Home | B News Letter | Top Sector Rotation Stocks "Sector Price Status Sector Volume Status Last 12 Months Sector Returns | PORTFOLIOS | Thr | @ Alpha Folio | nth | Dark | v 12 | 4.00 | S Quant Model Portfolios | Cea | Banking | 0.00: | © Alpha 30 | Development Bank
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 075. `Screenshot 2026-10-16 at 2.37.16 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market overview / sector and breadth dashboard
- **What it represents:** The screen appears to compare market or sector conditions using compact cards, tables, charts and/or color-coded summaries. Color and relative size encode category/performance at a glance; exact mappings should be verified against the full-size image.
- **Data representation:** Dashboard cards, time-series charts, tables, and/or distribution plots; precise encoding depends on the individual panel.
- **OCR evidence (best effort):** Model Protfolio Sastoshare V.1.1 Nepse Alpha | Nepse Alpha | MARKET | Alpha 30 Stocks | Overall Performance | Running Quarter | Two Quarters Back | PORTFOLIOS | @ Alpha Folio | + 10% | anf | S Quant Model Portfolios | 2 047.63 (+1 984.83%) | -10% | © Alpha30 | O Stock List | + 1500 | -5% | -30% | O Performance | 25. Jul | 8. Aug
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 076. `Screenshot 2026-10-16 at 2.37.33 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** go s | Live Trading Scan Sastoshare V.1.1 Nepse Alpha | Alp | Me Live Trading | Live Trading Scan | www.youtube.com - To exit full screen, press | esc | @ nepsealpha.com/sastoshare/live-trading-scan | A Alo | 4 Live Trading > Live Trading Scan | O Price & Ratio's Compare | Select Time Frame | Commercial Banks | O Chart Compare | Daily Chart | 1 Minutes Chart | TRADING & INVESTING | cities | l@ Charting | 15 Minutes Chart | 30 Minutes Chart | 60 Minutes Chart | © Trading Chart | As of Sep 8th 2022, 2:59:40 pm
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 077. `Screenshot 2026-10-16 at 2.37.40 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** Tra | Aya Nepsé | nepsealpha.com | > Alba: | @ Sastoshar | ven | x @ | ©) Financial Comparison | 4B Live Trading > Live Trading Scan | © Custom Compare | Select Time Frame | Commercial Banks | O Price & Ratio's Compare | O Chart Compare | Daily Chart | 1 Minutes Chart | TRADING & INVESTING | l@ Charting | 15 Minutes Chart | 30 Minutes Chart | 60 Minutes Chart | © Trading Chart
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 078. `Screenshot 2026-10-16 at 2.37.46 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** andle | Ay Nepsé | nepsealpha.com | > Alba: | x @ | @ Sastoshare | ©) Financial Comparison | # Live Trading > Candlestick | © Custom Compare | O Price & Ratio's Compare | Daily 5 Minute 15 Minute 30 Minute “Hours: | O Chart Compare | In Decision | Doji | TRADING & INVESTING | © Doji | \@ Charting | Symbol | Full Name | LTP | Bullish | © Trading Chart
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 079. `Screenshot 2026-10-16 at 2.37.50 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** Tra | idle | Iya Nepsé | nepsealpha.com | > Alba: | Hammer | ENL | Emerging Nepal Limited | NPR 653.00 | @ Sastoshare | Bullish Harami | © Financial Comparison | FMDBL | First Micro Finance Development | NPR 678.00 | © Custom Compare | Dragonfly Doji | Bank Ltd. | Inverted Hammer | O Price & Ratio's Compare | Bullish Marubozu | GLH
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 080. `Screenshot 2026-10-16 at 2.37.54 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** Ay Nepsé | nepsealpha.com | > Alba: | x @ | @ Sastoshare | ©) Financial Comparison | @ Live Trading > Candlestick | © Custom Compare | Daily | 5 Minute | 15 Minute | O Price & Ratio's Compare | 30 Minute Hours | O Chart Compare | In Decision | Tweezer Bottom | TRADING & INVESTING | Doji | l@ Charting | Symbol | Full Name | LTP
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 081. `Screenshot 2026-10-16 at 2.37.56 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** Ay Nepsé | @ nepsealpha.com, | > Alba: | @ Sastoshare | x @ | ©) Financial Comparison | 4B Live Trading > Auto Fibonacci Scan | O Custom Compare | Sasto Share / Auto Fibonacci | O Price & Ratio's Compare | @ © upnearThis Range | All | Search Symbol | O Chart Compare | Up trending Fibonacci Retardment Levels | TRADING & INVESTING | l@ Charting | Symbol | 23.6% 38.2% 50% 61.8% | 61.8% 50% = - 38.2% | 23.6% | ADBL
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 082. `Screenshot 2026-10-16 at 2.38.00 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** Tra | Ay ty Nepsé | @ nepsealpha.com | > Alia: | @ Sastoshare | x @ | © Financial Comparison | 4B Live Trading > Auto Fibonacci Scan | © Custom Compare | Sasto Share / Auto Fibonacci | O Price & Ratio's Compare | @ © uppnearthis Range | All | Search Symbol | O Chart Compare | Up trending Fibonacci Retardment Levels | TRADING & INVESTING | ‘Down trending Fibonacci Retardment Levels | l@ Charting | Symbol | 23.6% | 38.2% 50% 61.8%
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 083. `Screenshot 2026-10-16 at 2.38.04 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** e Tra | vay Népsé | nepsealpha.com | > Alba | @ Sastoshar | van | x @ | UU Financial Comparison | 4B Live Trading > Volume Scan | © Custom Compare | TOP 20 High Volume (Kitta) | Top 20 Relative Volume | Volume Today Highest 20 days | Volume Today Lowest 20 days | O Price & Ratio's Compare | O Chart Compare | 400k | TRADING & INVESTING | l@ Charting | 300k | © Trading Chart | lm NEPSE Breadth
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 084. `Screenshot 2026-10-16 at 2.38.13 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** fy Népsé | @ nepsealpha.com | 2 Alrpa: | @ Sastoshare | U) Financial Comparison | O Custom Compare | Fl E | O Price & Ratio's Compare | ke) | eed | Re) | xs x & | O Chart Compare | fea | TRADING & INVESTING | l@ Charting | © Trading Chart | Volume Today Lowest 20 days | l@ NEPSE Breadth | HIDCLP | Investment | NPR 103.00
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 085. `Screenshot 2026-10-16 at 2.38.16 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** e Tra | Népsé | nepsealpha.com | > Alga | @ Sastoshare | x @ | ©) Financial Comparison | 4B Live Trading > Live Trading Scan | O Custom Compare | Select Time Frame | O Price & Ratio's Compare | Commercial Banks | O Chart Compare | Daily Chart | 1 Minutes Chart | TRADING & INVESTING | l@ Charting | 15 Minutes Chart | 30 Minutes Chart | 60 Minutes Chart | © Trading Chart | As of Sep 8th 2022, 2:59:40 pm
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 086. `Screenshot 2026-10-16 at 2.38.23 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Market chart / technical-analysis workspace
- **What it represents:** Price history is represented as a candlestick time series, with volume bars beneath the price chart and charting/drawing controls around the plot. The screenshot supports a chart-workspace interpretation; exact indicator values and all control labels require full-resolution manual confirmation.
- **Data representation:** Time-series chart, likely candlesticks and/or overlays; volume may be shown as bars beneath price.
- **OCR evidence (best effort):** Aw Nepsé | nepsealpha.com | > Alia: | @ Sastoshare | x @ | © Financial Comparison | 4 Live Trading > Live Trading Scan | © Custom Compare | Select Time Frame | O Price & Ratio's Compare | Commercial Banks | O Chart Compare | Daily Chart | 1 Minutes Chart | TRADING & INVESTING | l@ Charting | 15 Minutes Chart | 30 Minutes Chart | 60 Minutes Chart | © Trading Chart | As of Sep 8th 2022, 2:59:40 pm | l@ NEPSE Breadth
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 087. `Screenshot 2026-10-16 at 2.38.31 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 088. `Screenshot 2026-10-16 at 2.38.34 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 089. `Screenshot 2026-10-16 at 2.38.42 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 090. `Screenshot 2026-10-16 at 2.38.44 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 091. `Screenshot 2026-10-16 at 2.38.45 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 092. `Screenshot 2026-10-16 at 2.38.48 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 093. `Screenshot 2026-10-16 at 2.38.51 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 094. `Screenshot 2026-10-16 at 2.38.59 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 095. `Screenshot 2026-10-16 at 2.39.05 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 096. `Screenshot 2026-10-16 at 2.39.09 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 097. `Screenshot 2026-10-16 at 2.39.13 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 098. `Screenshot 2026-10-16 at 2.39.17 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 099. `Screenshot 2026-10-16 at 2.39.22 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 100. `Screenshot 2026-10-16 at 2.39.32 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 101. `Screenshot 2026-10-16 at 2.39.44 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 102. `Screenshot 2026-10-16 at 2.39.48 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 103. `Screenshot 2026-10-16 at 2.39.50 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 104. `Screenshot 2026-10-16 at 2.39.52 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 105. `Screenshot 2026-10-16 at 2.39.55 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

### 106. `Screenshot 2026-10-16 at 2.39.57 PM.png`

- **Image dimensions:** 2880 × 1800px
- **Screen interpretation:** Trading-platform screen (text not confidently classified)
- **What it represents:** The screenshot is a screen from the trading/analytics application. OCR did not yield enough unambiguous text to assign a narrower function confidently. The image is retained as a separate evidence record; review the embedded screenshot and OCR extract before converting this into a definitive requirement.
- **Data representation:** Card-based strategy chooser or filtered/ranked security table.
- **OCR evidence (best effort):** No usable OCR text captured; inspect image directly.
- **Data-field caution:** Exact numerical values and small labels are not asserted unless legible in the OCR extract.
- **Mega Tool implication:** Preserve as an independent requirement candidate; confirm labels, units, periods, filters and source/provenance before implementation.

