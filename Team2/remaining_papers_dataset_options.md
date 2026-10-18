# Datasets for Remaining Very-High-Potential Papers (Score 9/10)

Companion to `stealthy_shorts_dataset_options.md` (Hyperliquid dataset already covered for Stealthy Shorts).

---

# 1. Credit Card Fraud Detection — Chan et al. (1999) — BaoHuy

**Paper:** Distributed data mining, metalearning, cost-sensitive learning (AdaCost) for credit card fraud.

## 🏆 Primary: ULB Credit Card Fraud Detection (mlg-ulb)
**URL:** https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud
**Quality: 9.5/10** — The de-facto academic benchmark (used in hundreds of papers).

| Property | Value |
|---|---|
| Rows | 284,807 transactions (2 days of European cardholders) |
| Fraud rate | 492 frauds = **0.172%** (extreme imbalance — matches paper's challenge) |
| Features | 28 PCA components (V1–V28) + Time + Amount |
| Task | Binary classification |

**Fit to the paper:**
- Extreme class imbalance → motivation for **cost-sensitive learning** (AdaCost) and ensemble/metalearning exactly as in Chan et al.
- Perfect for testing whether **combining classifiers beats single classifiers** (the paper's core claim).
- `Amount` + `Time` support cost-weighted evaluation (fraud loss vs transaction value).

**Limitation:** PCA-anonymized features → no interpretable feature engineering, no merchant/customer structure.

## 🥈 Complement A: Synthetic Credit Card Fraud — Interpretable 1M
**URL:** https://www.kaggle.com/datasets/harshjain123/synthetic-credit-card-fraud-interpretable
**Quality: 8.5/10**

- 1,000,000 transactions, 50,000 customers, ~180 days, **1.9% fraud rate**
- **27 named, interpretable features**: geo-velocity, transaction velocity, IP risk, card-present flag, foreign transaction, time-of-day
- Gradient-boosted baseline: ROC-AUC ≈ 0.83, PR-AUC ≈ 0.19 (hard but solvable)
- CC0 license, generator script included (seed=42, fully reproducible)

**Use for:** SHAP explainability, feature-importance analysis, threshold/business-cost optimization — impossible on the PCA dataset.

## 🥈 Complement B: Enterprise Fraud Detection Dataset
**URL:** https://www.kaggle.com/datasets/mohamedasak/enterprise-fraud-detection-dataset
**Quality: 8/10**

- 200K transactions, 44 features, ~2.8% fraud rate, 4–5 fraud types (card testing, identity theft, account takeover, **fraud ring**)
- Includes **graph/network features** (fraud rings, shared devices) — directly supports the "distributed" architecture angle of Chan et al.
- Velocity windows (1h/24h/7d), device fingerprinting, geolocation

## 💡 Also worth knowing
- **PaySim** (`ntnu-testimon/paysim1`): 6.3M synthetic mobile-money transactions — standard second dataset for cross-domain validation (used in recent published fraud studies).
- **IEEE-CIS Fraud Detection** (Vesta, Kaggle competition): ~590K real transactions, 400+ features, harder and more realistic; strong choice if you want a "real-data" extension.

## Recommended experiment design (mirrors the paper)
1. Split data into subsets → train parallel base classifiers (DT, LR, NB, MLP) per subset → **stack via metalearning**.
2. Compare single vs combined classifiers on **cost-sensitive metrics** (fraud loss, recall at fixed FPR), not just AUC.
3. Run cost-sensitive variants (AdaCost / class weights / focal loss) on top.
4. Validate on ULB (real) + Interpretable-1M (explainable) → strongest report card.

---

# 2. Deep Learning for Credit Scoring: Do or Don't? — Gunnarsson et al. (2021) — BaoHuy

**Paper:** Compares MLP + DBN vs LR, DT, RF, XGBoost on 10 real credit datasets, with Bayesian hypothesis testing and profit-driven metrics. Verdict: XGBoost wins; DL doesn't beat shallow models.

## 🏆 Primary: Give Me Some Credit (GMSC)
**URL:** https://www.kaggle.com/c/GiveMeSomeCredit
**Quality: 9.5/10** — The standard credit-scoring benchmark in both academia and industry.

| Property | Value |
|---|---|
| Rows | 150,000 train / 101,503 test |
| Target | `SeriousDlqin2yrs` (90+ days past due) |
| Default rate | ~6.7% (imbalanced) |
| Features | 10 (RevolvingUtilization, age, #delinquencies, DebtRatio, MonthlyIncome, #open loans...) |

**Fit to the paper:**
- Gunnarsson et al.'s core finding (XGBoost ≥ shallow ≥ DL) is directly replicable here.
- Well-documented **cost matrix** exists (Empulse library docs: loss-given-default 75%, credit line, profit framework) → enables the paper's **profit-driven evaluation**, not just AUC.
- Named features → monotonicity/fairness analysis possible (used in NAM/MNAM literature with published LR/FCNN/NAM baselines: AUC ≈ 0.78–0.80 to compare against).

## 🥈 Complement A: Home Credit Default Risk
**URL:** https://www.kaggle.com/c/home-credit-default-risk
**Quality: 9/10**

- 307K applicants **across 7 relational tables** (application, bureau, previous loans, credit card balance...)
- Multi-table → rewards feature engineering / aggregation pipelines
- ROC-AUC evaluation; massive kernel library for baselines

**Use for:** scaling the study — does XGBoost's advantage hold when features are engineered well? Does DL gain anything with rich features? (Spoiler per the paper: no — that's the point.)

## 🥈 Complement B: Classic UCI benchmarks (the paper used 10 datasets — these are the public classics)
| Dataset | N | Default % | Source |
|---|---|---|---|
| German Credit | 1,000 | 30% | UCI Statlog |
| Australian Credit | 690 | 56% | UCI |
| Japanese Credit | 690 | ~56% | UCI |
| Taiwan Default of Credit Card Clients | 30,000 | ~22% | UCI |

**Use for:** multi-dataset robustness exactly like the paper (Baesens 2003 / Lessmann 2015 style). Small but historically canonical; run paired Bayesian significance tests (as the paper does) across GMSC + these.

## Recommended experiment design (mirrors the paper)
1. Models: LR, DT, RF, XGBoost, LightGBM vs MLP + DBN (the paper's DL pair).
2. Metrics: AUC + **H-measure** + **profit/expected-cost** (GMSC cost matrix).
3. 10 real datasets → paired comparisons → Bayesian hypothesis testing (e.g., Bayesian correlated t-test / Wilcoxon).
4. Report when DL wins/loses → replicate the "Do or Don't" verdict.

---

# 3. Code Revert Prediction with GNN — Pei et al. (2023) — NguyenSyHuynh

**Paper:** Predict risky code commits (reverts) at J.P. Morgan using GNNs over import-dependency graphs; <4% positive rate; features: 30-day revert frequency, file version, commit-push delay, LOC, cyclomatic complexity, contributors.

## 🏆 Primary: Defectors (Zenodo, open access)
**URL:** https://zenodo.org/records/7708984
**Quality: 9/10** — Largest modern open defect-prediction dataset, built for deep learning.

| Property | Value |
|---|---|
| Scale | ~213K Python files: ~93K defective / ~120K clean |
| Projects | 25 popular Python repos (ML, automation, IoT domains) |
| Labeling | **Bug-inducing commits mapped via SZZ** (`bug_inducing_commits.zip` + filtered YAML) |
| Tasks supported | **Just-in-time (commit-level)** + line-level defect prediction |

**Fit to the paper:**
- Commit-level (JIT) framing matches "predict risky commits before they cause reverts."
- Per-commit file lists → build **file co-change / import-dependency graphs** → GNN (GCN/GAT via PyTorch Geometric or DGL) — the paper's core method.
- Imbalance controllable: aggregate to commit granularity where defective commits are rarer.
- Reproducible: repo links + filtering criteria published.

## 🥈 Complement A: GHPR Dataset
**URL:** https://github.com/feiwww/GHPR_dataset
**Quality: 7.5/10**

- 3,026 bug-fixing pull requests → 6,052 instances (defective vs fixed file version)
- 16 fields incl. `OLD_CONTENT` / `NEW_CONTENT` (pre/post-fix code), commit description, diff code, timestamps
- CSV + SQL formats

**Use for:** defect-inducing vs fixed code pairs; text/metric features; smaller → fast iteration.

## 🥈 Complement B: PyTraceBugs
**URL:** https://github.com/acheshkov/pytracebugs
**Quality: 7.5/10**

- Python functions/methods labeled buggy (from bug-fix commits linked to GitHub issues) vs stable
- `before_merge` / `after_merge` snippets + tracebacks; train/val/test splits ready

## 🥉 Complement C: AmadeusGitHubBugDataset
**URL:** https://github.com/AmadeusGitubBugProject/AmadeusGithubBugDataset → https://github.com/AmadeusBugProject/AmadeusGithubBugDataset
**Quality: 7/10**

- 54,755 bug-labeled issues from 103 GitHub projects; 10,459 "benchmark-ready" with commit metadata, Java-aware diffs, change location to method level
- Includes manually verified training set (concurrency / memory / semantic bugs)

## 🥉 Complement D (Kaggle-native): GitHub Bugs Prediction
**URL:** https://www.kaggle.com/datasets/anmolkumar/github-bugs-prediction
**Quality: 6.5/10**

- 150K train + 300K extra rows: classify GitHub issues (Bug / Feature / Question) from title+body
- Text-level only (no commit/graph structure) — a warm-up task, not the core GNN project

## 🛠 Building the graph (the missing piece)
No public dataset ships prebuilt import graphs. Recreate the paper's setup:
1. Take Defectors repos (links in `repo_links.yaml`) or any live GitHub repos.
2. Parse `import` statements (Python `ast`) → file-level dependency edges.
3. Commit features via **PyDriller** (30-day revert/fix frequency, commit-push delay, LOC churn, contributors, cyclomatic complexity via `radon`).
4. Labels: SZZ-mapped bug-inducing commits (Defectors) or mined `Revert "<sha>"` commits via GitHub API (closest to the paper's own labeling).
5. Train GNN (GCN/GAT) vs GBDT baseline on handcrafted features → the paper's comparison.

---

# 4. JEL: Neural Entity Linking at JPMorgan — Ding et al. (2021) — NguyenSyHuynh

**Paper:** Link company mentions in financial news to a proprietary knowledge graph without Wikipedia; Wide & Deep architecture, margin-loss entity embeddings, n-gram cosine similarity beating Jaccard/Levenshtein/Jaro-Winkler.

## 🏆 Primary (corpus): Financial News Articles — webz.io free dump / FiNER-ORD corpus
**URL (corpus):** https://webz.io/free-datasets/financial-news-articles/
**URL (research dataset + models):** https://huggingface.co/datasets/gtfintechlab/finer-ord — https://github.com/gtfintechlab/FiNER
**Quality: 8.5/10**

| Property | Value |
|---|---|
| Articles | 47,851 English financial news (JSON with source, date, author, title) |
| Gold labels | 201 articles manually annotated PER / LOC / ORG (Doccano, span-level) |
| License | CC BY-NC 4.0 (fine for coursework; check for commercial use) |
| Baselines published | RoBERTa-base F1 ≈ 0.89 weighted (beats FinBERT; LLMs underperform PLMs) |

**Fit to the paper:** This is a news corpus of exactly the type JEL ingests. Pipeline: NER (train on 201 gold articles) → candidate generation → **linking/ranking** (the JEL core).

## 🏆 Primary (evaluation gold): Financial Named Entity Normalization Dataset
**URL:** https://github.com/sjeon7/Financial-Named-Entity-Normalization-Dataset
**Quality: 9/10 for the linking step** — the closest public gold set to JEL's task.

- 7,155 unique ORG entities from S&P 500 10-K business sections → hand-grouped into **2,600 identity groups**
- 25,000 pairs: 10,825 positive / 14,175 negative
- Covers precisely JEL's hard cases: synonyms (Coca-Cola® / Coca-Cola), abbreviations (Baker Hughes company / Co), acronyms (Amazon Web Services / AWS, NYSE), punctuation variants, descriptive phrases (EY formerly Ernst & Young), NER parse errors

**Fit to the paper:** = the "link mention → canonical entity" ground truth. Benchmark exactly the string-similarity methods the paper compared (n-gram cosine vs Jaccard vs Levenshtein vs Jaro-Winkler), then add the neural matcher (Wide & Deep / dual-encoder with margin loss) and show where embeddings win.

## 🥈 Complement A: FiNER-139 (XBRL tagging)
**URL:** https://huggingface.co/datasets/nlpaueb/finer-139
**Quality: 8/10**

- 1.1M sentences from ~10K SEC filings (2016–2020), 139 gold XBRL entity types, IOB2 scheme
- Different flavor of financial entity extraction (numeric tokens tagged by context) — good *extension*: entity typing beyond company linking, with published SEC-BERT/FinBERT baselines

## 🥈 Complement B: Ticker-mapped news for end-to-end linking
**URL:** https://huggingface.co/datasets/athetus/intl-market-news
**Quality: 7/10**

- GDELT financial news with **curated ticker maps** (company name ↔ yfinance symbol ↔ aliases) for TWSE/B3 markets; tone scores included
- Use as a knowledge-graph stand-in: link news mentions → tickers → evaluate against the provided mappings (analogous to JEL's internal KG)

## 🛠 Building the knowledge graph (the missing piece)
JEL's internal KG isn't public. Free stand-ins:
- **SEC EDGAR company_tickers.json** (free, official): company name ↔ ticker ↔ CIK — the canonical entity dictionary for US firms
- Kaggle/Nasdaq ticker lists for symbols + sector metadata
- Entity linking eval: mention string from news (FiNER-ORD corpus) → predict ticker/CIK → check against gold (NEN dataset + ticker maps)

## Recommended experiment design (mirrors the paper)
1. **NER stage:** fine-tune spaCy / RoBERTa on FiNER-ORD gold (201 articles).
2. **Candidate generation:** BM25 / n-gram cosine over EDGAR company names + aliases.
3. **Ranking stage:** (a) string metrics — n-gram cosine, Jaccard, Levenshtein, Jaro-Winkler (paper's exact set); (b) neural — Wide & Deep or sentence-transformers fine-tuned with **margin loss** on NEN pairs.
4. Evaluate on the NEN pair classification + end-to-end mention→ticker accuracy.
5. Ablate: no-context vs context features (paper's "minimal context + margin loss" claim).

---

# 📊 Master Comparison

| Paper | 🏆 Dataset | Size | Gold labels? | License | Difficulty |
|---|---|---|---|---|---|
| Fraud Detection (Chan 1999) | mlg-ulb creditcardfraud (+ Interpretable-1M) | 285K / 1M | ✅ Class | Public | ⭐⭐ Easy |
| Credit Scoring (Gunnarsson 2021) | Give Me Some Credit (+ Home Credit, UCI classics) | 150K / 307K | ✅ Default | Public | ⭐⭐ Easy |
| Code Revert GNN (Pei 2023) | Defectors (+ GHPR, PyTraceBugs) | 213K files | ✅ SZZ commits | Open (Zenodo) | ⭐⭐⭐⭐ Hard |
| Entity Linking (Ding 2021) | FiNER-ORD corpus + NEN gold (+ EDGAR KG) | 47.8K news + 7.1K entities | ✅ NER + pairs | CC BY-NC 4.0 | ⭐⭐⭐ Medium |

**Availability note:** Unlike Stealthy Shorts (where the ideal equity-level data is proprietary), **all four papers above have fully public, gold-labeled data** — the 9/10 scores hold without data-access caveats, except:
- Defectors requires you to **construct** dependency graphs yourself (that construction *is* part of the project's learning value).
- JEL requires you to **assemble** a stand-in knowledge graph (EDGAR) — also part of the intended work.
