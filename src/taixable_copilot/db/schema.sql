-- Cross-Border Tax Copilot — system-of-record schema (Cloud SQL for MySQL).
-- Mirrors the SQLAlchemy metadata in repository.py. Synthetic, non-PII data only.

CREATE TABLE IF NOT EXISTS customers (
    id               INT AUTO_INCREMENT PRIMARY KEY,
    customer_token   VARCHAR(64) NOT NULL UNIQUE,
    display_label    VARCHAR(255),
    residence_country CHAR(2) NOT NULL
);

CREATE TABLE IF NOT EXISTS compliance_cases (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    customer_id       INT NOT NULL,
    tax_year          INT NOT NULL,
    primary_residence CHAR(2) NOT NULL,
    summary           TEXT,
    status            VARCHAR(32) NOT NULL DEFAULT 'open',
    approved_by       VARCHAR(255),
    created_at        DATETIME NOT NULL,
    CONSTRAINT fk_case_customer FOREIGN KEY (customer_id) REFERENCES customers(id)
);

CREATE TABLE IF NOT EXISTS case_deadlines (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    case_id      INT NOT NULL,
    jurisdiction CHAR(2) NOT NULL,
    description  VARCHAR(512) NOT NULL,
    due_date     CHAR(10) NOT NULL,
    citation_id  VARCHAR(128),
    CONSTRAINT fk_deadline_case FOREIGN KEY (case_id) REFERENCES compliance_cases(id)
);

CREATE TABLE IF NOT EXISTS case_citations (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    case_id     INT NOT NULL,
    citation_id VARCHAR(128) NOT NULL,
    CONSTRAINT fk_citation_case FOREIGN KEY (case_id) REFERENCES compliance_cases(id)
);
