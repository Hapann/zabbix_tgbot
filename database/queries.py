CREATE_TABLE_INCIDENTS = """
CREATE TABLE IF NOT EXISTS incidents (
    id SERIAL PRIMARY KEY,
    event TEXT NOT NULL,
    node TEXT NOT NULL,
    trigger TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    details TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    assigned_to_username TEXT,
    assigned_to_user_id INTEGER,
    closed_by_username TEXT,
    closed_by_user_id INTEGER,
    closed_at TIMESTAMP WITH TIME ZONE,
    comment TEXT
);
"""

INSERT_INCIDENT = """
INSERT INTO incidents (
    event, 
    node, 
    trigger, 
    status, 
    severity, 
    details,
    assigned_to_username,
    assigned_to_user_id,
    closed_by_username,
    closed_by_user_id
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
RETURNING id;
"""

UPDATE_STATUS = """
UPDATE incidents
SET status = $1,
    updated_at = NOW(),
    assigned_to_username = $2,
    assigned_to_user_id = $3,
    comment = COALESCE(comment, '') || '\n' || $4
WHERE id = $5
RETURNING id;
"""

CLOSE_INCIDENT = """
UPDATE incidents
SET status = 'closed',
    closed_by_username = $1,
    closed_by_user_id = $2,
    closed_at = NOW(),
    comment = COALESCE(comment, '') || '\n' || $3,
    updated_at = NOW()
WHERE id = $4
RETURNING id; 
"""

REJECT_INCIDENT = """
UPDATE incidents
SET status = 'rejected',
    closed_by_username = $1,
    closed_by_user_id = $2,
    closed_at = NOW(),
    comment = COALESCE(comment, '') || '\n' || $3,
    updated_at = NOW()
WHERE id = $4
RETURNING id;  
"""