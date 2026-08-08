# Project Context: Enterprise Sanctions Screening Agent


## 1. Project Objective

This project aims to build an enterprise sanctions screening system.

The system is designed to identify whether companies, individuals, vessels, suppliers, customers, or beneficial owners are associated with international sanctions lists.

The ultimate goal is to provide an explainable and auditable compliance risk screening solution.


---

## 2. Business Background

In international trade, insurance, and supply chain management, transactions may involve sanctioned entities.

The system should help companies:

- screen counterparties before transactions;
- reduce sanctions compliance risks;
- improve due diligence efficiency;
- provide evidence-based screening reports.


---

## 3. Current Data Sources

Current:

- OFAC SDN List (Advanced XML)


Future:

- UK Sanctions List
- EU Consolidated Financial Sanctions List
- UN Security Council Sanctions List
- Other international compliance databases


---

## 4. Current Technology Stack

Programming Language:

- Python


Main Libraries:

- lxml (XML parsing)
- requests (data retrieval)
- supabase-py (database interaction)
- rapidfuzz (name similarity matching)


Database:

- Supabase PostgreSQL


Development Environment:

- PyCharm
- Git


---

## 5. Current System Architecture


Data Sources

        ↓

XML/API Data Acquisition

        ↓

Data Parser

        ↓

Data Normalization

        ↓

Database Storage

        ↓

Entity Matching Engine

        ↓

Risk Assessment

        ↓

Screening Report


---

## 6. Current Database Design


Main tables:


### sanctions_entities

Stores sanctioned entities.

Fields include:

- entity name
- entity type
- source
- profile ID
- entry ID
- program
- address


### sanctions_names

Stores normalized names and aliases.

Purpose:

Improve entity matching performance.


---

## 7. Current Development Progress


Completed:

- OFAC Advanced XML structure analysis
- XML namespace handling
- Profile extraction
- Alias extraction
- Location extraction
- Program extraction
- Supabase connection


In Progress:

- Data normalization
- Name matching algorithm
- Entity type mapping
- Batch data import optimization


---

## 8. Key Technical Challenges


### 8.1 Multilingual Name Normalization

Sanctions lists contain:

- English names
- Arabic names
- Hebrew names
- Cyrillic names
- Other transliteration forms


The system must balance:

- high recall
- low false positive rate


---

### 8.2 Entity Resolution

The same entity may appear as:

Example:

Abu Ubaidah

Abu Ubaydah

Abu Ubayda


The system should determine whether different names refer to the same entity.


---

### 8.3 False Positive Control

A sanctions screening system should not only find possible matches.

It must also:

- provide confidence scores;
- explain matching reasons;
- support human review.


---

## 9. Development Principles


When modifying code:

1. Prioritize correctness over simplicity.

2. Consider data quality and auditability.

3. Avoid introducing excessive false positives.

4. Keep modules independent and maintainable.

5. Provide explanations for important decisions.


---

## 10. Future Roadmap


Phase 1:

Complete sanctions database construction.


Phase 2:

Build entity matching engine.


Phase 3:

Develop API service using FastAPI.


Phase 4:

Integrate with AI Agent platforms.


Phase 5:

Provide enterprise compliance screening service.
