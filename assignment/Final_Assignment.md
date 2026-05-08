**AI-Assisted Financial Transactions Platform Assignment**

## **Overview**

You have been recruited by **Lumina Capital**, a fictional investment company, to build a mini full-stack financial transactions platform.

The system should:

* Ingest transaction data   
* Process and compute portfolio positions   
* Detect business rule violations   
* Provide analytics insights   
* Expose data through an API   
* Present results via a simple frontend 

## **Mandatory Requirement – AI Usage**

This assignment **MUST** be completed using AI tools (ChatGPT, Claude, Cursor, Copilot, etc.).

* You are responsible for validating all generated code   
* You must fully understand your solution   
* The system must run successfully end-to-end 

You must include a file named **AI\_USAGE.md** with:

* AI tools used   
* Example prompts   
* What code was generated   
* What you modified   
* Mistakes and how you fixed them 

## **Estimated Time**

3–5 hours

## **Technical Requirements**

* Backend: Python (FastAPI preferred)   
* Database: SQLite (minimum)   
* Frontend: Simple UI (React or HTML/JS)   
* Code must be clean, modular, and runnable 

## **Input**

transactions\_sample.xlsx containing:

* ClientId   
* TransactionId   
* ISIN   
* Action (Buy/Sell)   
* Quantity   
* Price   
* Timestamp 

## **Part A – Data Ingestion & Validation**

* Load and parse the Excel file   
* Normalize data 

Validation rules:

* Quantity \> 0   
* Price \> 0   
* Action must be Buy or Sell 

## **Part B – Backend API**

Implement the following endpoints:

* POST /upload-transactions   
* GET /clients   
* GET /clients/{client\_id}/positions   
* GET /violations   
* GET /analytics 

## **Part C – Business Logic**

* FIFO cost calculation   
* Realized and unrealized P\&L   
* Positions per ISIN 

## **Part D – Rule Violations**

* **Day Trading Detection**  
  More than 3 buy/sell pairs within 24 hours → flag as *Day Trading*   
* **Risk Concentration**  
  One ISIN \> 50% of portfolio → flag as *Potential Risk*   
* **Sell Before Buy**  
  Flag as *ERROR*   
* **Invalid Values**  
  Price or Quantity \< 0 → flag as *ERROR* 

## **Part E – Storage**

Instead of storing data only in memory or files, your system must persist data in a database.

### **Requirements:**

* Use SQLite as a minimum requirement   
* Use an ORM (e.g., SQLAlchemy) – preferred   
* Design a simple schema with at least the following tables:   
  * transactions   
  * positions   
  * violations 

### **Expectations:**

* Data should be stored after processing the uploaded file   
* API endpoints must retrieve data from the database (not in-memory)   
* The system should support reloading data after restart 

### **Bonus (optional):**

* Separation between raw transactions and computed positions   
* Basic indexing or optimization 

## **Part F – Analytics**

Your system should compute and expose meaningful analytics through the API.

### **Required analytics:**

* Top 3 most traded ISINs (by number of transactions)   
* Average holding time per client   
* Most volatile client (largest variation in total portfolio value)   
* ISIN concentration report:   
  * ISINs appearing in more than 70% of clients   
  * Include list of clients holding each ISIN 

### **Expectations:**

* Analytics must be based on processed data   
* Should be accessible via API (GET /analytics)   
* Output should be structured (JSON format) 

### **Bonus (optional):**

* Caching or optimization   
* Additional insights 

## **Part G – Frontend**

Build a simple UI that interacts with your backend API.

### **Requirements:**

* Upload the Excel file via UI   
* Display results retrieved from the API 

### **The UI must include:**

* File upload button   
* Table displaying positions per client   
* Table displaying violations   
* Section displaying analytics 

### **Expectations:**

* The frontend must communicate with the backend via HTTP requests   
* Data must not be hardcoded   
* Basic usability is required (no need for design perfection) 

### **Allowed:**

* React (preferred)   
* Plain HTML \+ JavaScript 

### **Bonus (optional):**

* Loading indicators   
* Error handling   
* Basic styling 

## **Part H – Testing**

Include basic automated tests.

### **Minimum requirements:**

* At least 1 test for an API endpoint   
* At least 2 tests for business logic 

### **Examples:**

* FIFO calculation correctness   
* Detection of “sell before buy”   
* Validation of invalid inputs 

### **Expectations:**

* Use pytest (preferred)   
* Tests should be runnable via a simple command 

### **Bonus (optional):**

* Edge cases   
* Improved coverage 

## **Submission Requirements**

Submit a ZIP file containing:

### **Required:**

* Full source code   
* requirements.txt   
* README.md   
* AI\_USAGE.md 

### **README.md must include:**

* Project overview   
* Setup instructions   
* How to run backend   
* How to run frontend   
* How to run tests 

### **The system must:**

* Run locally without errors   
* Be easy to set up (clear instructions) 

### **Bonus (optional):**

* Dockerfile or docker-compose   
* Example API requests 

## **Evaluation Criteria**

We will evaluate your submission based on the following:

### **1\. Code Quality**

* Clean, readable, maintainable code   
* Proper structure and separation of concerns 

### **2\. System Design**

* Logical architecture   
* Clear separation between:   
  * API layer   
  * Business logic   
  * Data layer 

### **3\. AI Usage**

* Effective use of AI tools   
* Ability to validate and improve generated code   
* Demonstrated understanding (not blind usage) 

### **4\. Problem Solving**

* Correct implementation of logic (FIFO, validations, rules)   
* Handling edge cases 

### **5\. Execution**

* Code runs successfully   
* Instructions are clear   
* System works end-to-end 

