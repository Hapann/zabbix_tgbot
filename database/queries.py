CREATE_TABLE_INCIDENTS = """
CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    event TEXT NOT NULL,
    node TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    assigned_to TEXT,
    closed_by TEXT,
    closed_at TIMESTAMP,
    comments TEXT[]
);
"""

INSERT_INCIDENT = """
INSERT INTO incidents (event, node, trigger, status, severity, details)
VALUES ($1, $2, $3, $4, $5, $6)
RETURNING id;
"""

UPDATE_STATUS = """
UPDATE incidents
SET status = $1, updated_at = NOW(), assigned_to = $2, comments = array_append(comments, $3)
WHERE id = $4;
"""

CLOSE_INCIDENT = """
UPDATE incidents
SET status = 'closed', closed_by = $1, closed_at = NOW(), comments = array_append(comments, $2), updated_at = NOW()
WHERE id = $3;
"""

REJECT_INCIDENT = """
UPDATE incidents
SET status = 'rejected', closed_by = $1, closed_at = NOW(), comments = array_append(comments, $2), updated_at = NOW()
WHERE id = $3;
"""