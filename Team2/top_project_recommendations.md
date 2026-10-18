# Top Data Mining Project Recommendations - Team Analysis Summary

## Executive Summary

Based on analysis of 32 papers across 6 team members covering Finance, ML/DL applications, and Business Analytics, here are the papers with the **highest data mining project potential** (score 9/10):

---

## 🥇 Top 5 Papers for Data Mining Projects

### 1. **Distributed Data Mining in Credit Card Fraud Detection** (Chan et al., 1999)
- **Team Member:** BaoHuy
- **Score:** 9/10
- **Why:** 
  - Classic data mining problem perfectly aligned with curriculum
  - Multiple advanced techniques: ensemble learning, metalearning, cost-sensitive learning (AdaCost)
  - Handles key challenges: scalability, class imbalance, asymmetric costs
  - Datasets readily available (Kaggle credit card fraud datasets)
  - Clear evaluation metrics and business value
  - Directly replicable and extendable

### 2. **Deep Learning for Credit Scoring: Do or Don't?** (Gunnarsson et al., 2021)
- **Team Member:** BaoHuy
- **Score:** 9/10
- **Why:**
  - Rigorous comparative methodology (DL vs traditional ML)
  - Multiple algorithms: DBN, MLP, XGBoost, Random Forest, Logistic Regression
  - Credit scoring datasets available (Kaggle, UCI ML Repository)
  - Includes profit-driven metrics beyond accuracy
  - Bayesian hypothesis testing for proper statistical comparison
  - Addresses timely question: when does DL actually help?
  - 10 real datasets used in original study

### 3. **Code Revert Prediction with Graph Neural Networks** (Pei et al., 2023)
- **Team Member:** NguyenSyHuynh
- **Score:** 9/10
- **Why:**
  - Novel problem formulation with strong technical depth
  - Graph Neural Networks + code dependency mining
  - Reproducible with GitHub repository data
  - Multiple DM angles: graph construction, imbalanced classification, anomaly detection
  - Feature engineering from commit metadata
  - Handles extreme class imbalance (<4% positive class)
  - Directly applicable to software quality improvement

### 4. **JEL: End-to-End Neural Entity Linking at JPMorgan Chase** (Ding et al., 2021)
- **Team Member:** NguyenSyHuynh
- **Score:** 9/10
- **Why:**
  - NLP + entity resolution - core data mining techniques
  - Financial news datasets accessible
  - Multiple components: NER, string matching, neural embeddings
  - Wide & Deep architecture implementation
  - Compare string similarity algorithms (n-gram, Jaccard, Levenshtein)
  - Clear industry application and evaluation
  - Can use company knowledge graphs or build custom ones

### 5. **Stealthy Shorts: Informed Liquidity Supply** (Goyal et al., 2025)
- **Team Member:** PhucHien
- **Score:** 9/10
- **Why:**
  - Market microstructure data mining
  - Trading pattern classification (liquidity providers vs demanders)
  - Order book analysis and limit order modeling
  - Predict informed vs uninformed short sellers
  - Rich feature space from order-level data
  - Excellent ML classification problem
  - *Caveat:* Requires access to order-level data which may be challenging

---

## 🥈 Strong Runner-Ups (Score 8/10)

### 6. **Persistent and Transitory Components of Firm Characteristics** (Baba-Yara et al., 2024)
- **Team Member:** VuNhan
- Feature engineering through decomposition, cross-sectional prediction
- Financial data accessible (CRSP, Compustat)

### 7. **Fearing the Fed: How Wall Street Reads Main Street** (Elenev et al., 2024)
- **Team Member:** MinhTriet
- Event-driven data mining, macro announcements + market reactions
- Could incorporate NLP on Fed communications

### 8. **Financial Returns to Household Inventory Management** (Baker et al., 2024)
- **Team Member:** PhucHien
- Unique consumer behavior angle with scanner data
- Optimization + prediction opportunities

### 9. **Financial Ratios, Discriminant Analysis and Corporate Bankruptcy** (Altman, 1968)
- **Team Member:** BaoHuy
- Classic Z-score model, excellent for classical vs modern ML comparison
- Highly replicable with public financial data

---

## 📊 Project Selection Matrix

| Paper | Data Availability | Technical Depth | Implementation Feasibility | Learning Value | Business Relevance |
|-------|------------------|----------------|---------------------------|----------------|-------------------|
| **Credit Card Fraud** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Credit Scoring DL** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Code Revert GNN** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **Entity Linking** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Stealthy Shorts** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 🎯 Recommendation by Project Type

### For **Traditional Data Mining Techniques**:
→ **Credit Card Fraud Detection** (Chan et al., 1999)
- Ensemble methods, metalearning, cost-sensitive learning
- Handles all classic DM challenges

### For **Deep Learning Comparison Study**:
→ **Credit Scoring: DL vs ML** (Gunnarsson et al., 2021)
- Rigorous experimental design
- Clear answer to "when to use DL?"

### For **Graph Mining**:
→ **Code Revert Prediction with GNN** (Pei et al., 2023)
- Novel application of graph neural networks
- Software engineering + DM intersection

### For **NLP + Data Mining**:
→ **Entity Linking at JPMorgan** (Ding et al., 2021)
- Financial NLP with clear evaluation
- Multiple algorithmic components

### For **Novel Business Application**:
→ **Household Inventory Management** (Baker et al., 2024)
- Unique angle on consumer behavior
- Optimization meets prediction

---

## 📋 Implementation Considerations

### Easiest to Implement:
1. Credit Card Fraud Detection - datasets on Kaggle, well-documented methods
2. Credit Scoring Comparison - multiple public datasets, clear methodology
3. Altman Z-score Extension - financial data readily available

### Most Technically Challenging:
1. Stealthy Shorts - requires specialized market microstructure data
2. Code Revert GNN - graph construction and GNN implementation complexity
3. Entity Linking - need financial news corpus and entity knowledge base

### Best Learning Experience:
1. Credit Scoring Comparison - learn when DL helps vs hurts
2. Credit Card Fraud - master handling imbalance and cost-sensitive learning
3. Code Revert GNN - exposure to graph neural networks

---

## 🚫 Papers to Avoid as Primary Projects

**Review/Survey Papers (Low Project Potential):**
- Deep Learning in Economics Review (Zheng et al., 2022) - Score 3
- DL for BA/OR Review (Kraus et al., 2020) - Score 3
- DRL in Economics Review (Mosavi et al., 2020) - Score 3

**Primarily Theoretical:**
- Kyle (1985) - Continuous Auctions - Score 4
- Miller (1977) - Divergence of Opinion - Score 4
- Myers (1977) - Corporate Borrowing - Score 4

*Note: These are excellent for background reading but don't define implementable DM projects directly.*

---

## 🎓 Final Recommendation

**If choosing ONE project for maximum impact:**

### 🏆 **Credit Card Fraud Detection** (Chan et al., 1999)

**Reasons:**
1. ✅ Perfect alignment with data mining curriculum
2. ✅ Multiple advanced techniques in one project
3. ✅ Datasets immediately available
4. ✅ Clear success metrics
5. ✅ High business relevance
6. ✅ Addresses real-world challenges (imbalance, cost-sensitivity, scalability)
7. ✅ Room for extension and innovation
8. ✅ Feasible within course timeframe

**Alternative if you want cutting-edge methods:**
### 🥈 **Code Revert Prediction with GNN** (Pei et al., 2023)
- Modern deep learning (GNNs)
- Novel problem formulation
- Reproducible with GitHub data
- Strong technical showcase

