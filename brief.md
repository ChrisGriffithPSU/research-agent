# Quant Research Agent - System Overview

## **Core Mission**
You're building an autonomous research assistant that delivers a curated daily digest of **actionable ML techniques and conceptual inspirations** specifically for building better predictive models in MFT (minutes to hours/daily) futures trading. The system's sole purpose is to fuel your research with implementable ideas for features, model architectures, and optimization techniques - letting you focus on coding and testing rather than searching for ideas.

---

## **Primary Responsibilities**

### **1. Intelligent Content Discovery**
The agent continuously monitors and extracts insights from:
- **Kaggle**: Award-winning notebooks showcasing proven ML techniques
- **HuggingFace**: Model architectures and implementation patterns
- **arXiv/SSRN**: Academic papers with practical applications (not pure theory)
- **General Internet Search**: Targeted searches for specific topics in:
  - Time series analysis and forecasting
  - Statistical techniques and transformations
  - Mathematics applicable to financial modeling
  - Orderflow and order book analytics (L2 data features)
  - General ML advances that could transfer to quant research
  - Adjacent domains (computer vision, NLP, etc.) that might inspire novel feature engineering

**Search Scope**: Casts a wide net beyond just financial ML - includes broader ML, statistics, math, and time series work that could be adapted to futures trading research.

### **2. Content Filtering & Quality Control**
The agent filters content through a specific lens:

**INCLUDE:**
- Application-based papers and notebooks (not purely theoretical)
- Techniques that can become features, data exploration methods, models, or optimization approaches
- Anything with extractable logic/algorithms you can implement
- Content of any age - recency doesn't matter, usefulness does
- Complexity at all levels - show everything regardless of difficulty

**EXCLUDE:**
- Pure theoretical work without practical application
- Content already presented in previous digests (maintain long-term memory)
- Dataset recommendations (you provide your own data)

**Filtering Philosophy**: "Can I use this in my research?" NOT "Will this definitely work?"

### **3. Intelligent Extraction & Synthesis**
For each discovered item, the agent extracts and synthesizes:
- **Title and source link**
- **Key methodology insights** - the core technique/approach explained clearly
- **Code/pseudocode snippets** - actual implementation logic when available
- **Application ideas** - multiple ways this could be adapted for your MFT futures research, including:
  - Potential features to engineer
  - Data exploration techniques to uncover patterns
  - Model architecture ideas
  - Optimization/fine-tuning methods

**Priority Focus Areas:**
1. Feature Engineering (highest priority)
2. Data Exploration & Idea Generation (highest priority)
3. Model Architecture Selection
4. Model Optimization & Fine-tuning

### **4. Daily Digest Generation**
The agent compiles findings into a structured daily digest:

**Structure:**
- Organized by category (Feature Engineering, Model Architecture, Optimization, Data Exploration, etc.)
- 10-15 high-signal items per digest (configurable)
- Quality over quantity - focused on actionable insights
- Each item formatted for immediate coding action

**Delivery:**
- Primary: Email digest sent daily
- Secondary: Web dashboard with digest display
- On-demand generation capability when you need fresh ideas

**Design Philosophy**: After reading the digest, you should be able to immediately start coding implementations - no additional research needed.

### **5. Learning & Personalization System**
The agent learns from your feedback to improve recommendations:

**Feedback Mechanisms:**
- You explicitly tag items you've implemented
- You rate digest items for quality/relevance
- System uses reinforcement learning to improve future recommendations

**Research Context:**
- Manually defined research themes: MFT futures trading, minutes-to-hours holding periods
- Focus on orderflow/L2 order book features for market microstructure understanding
- Mathematical/statistical representations of market behavior
- Not context-aware of current projects - you adapt your research to the digest, not vice versa

### **6. Historical Knowledge Management**
The agent maintains comprehensive historical access:

**Capabilities:**
- Search past digests (if dashboard implementation chosen)
- Semantic search to find relevant content without exact keywords
- Prevents duplicate content from appearing in new digests
- Builds a searchable knowledge base of all discovered techniques

---

## **What This System Does NOT Do**
To be crystal clear on boundaries:
- ❌ Does NOT integrate with your research API or trading systems
- ❌ Does NOT assess viability or predict which ideas will work
- ❌ Does NOT filter by implementation difficulty
- ❌ Does NOT track performance benchmarks or compare approaches
- ❌ Does NOT analyze gaps in your current research
- ❌ Does NOT provide datasets (you supply your own data)
- ❌ Does NOT focus on high-frequency/microsecond trading techniques
- ❌ Does NOT track specific researchers, conferences, or GitHub repos (at least not initially)

---

## **Success Criteria**
The system is successful when:
1. You wake up to 10-15 actionable, novel ideas each morning
2. You can immediately start coding implementations from the digest
3. The breadth of content exposes you to techniques you wouldn't have found manually
4. The system learns over time to surface more relevant content based on your feedback
5. You spend zero time searching for research ideas - 100% of your time on implementation and testing

---

## **The Big Picture**
This is your **autonomous research assistant** that handles the "idea generation" bottleneck in quant research. Instead of spending hours searching arXiv, scrolling through Kaggle, or hunting for novel techniques, the agent does that work 24/7 and delivers a curated, actionable briefing each morning. You wake up, read the digest, and immediately start building and testing - transforming your research workflow from "search for ideas" to "implement and validate."

The system's intelligence grows over time through your feedback, becoming increasingly aligned with what actually helps your research. It's not about finding the "perfect" technique - it's about maximizing the volume and diversity of implementable ideas you can test, since you won't know what works until you build it.