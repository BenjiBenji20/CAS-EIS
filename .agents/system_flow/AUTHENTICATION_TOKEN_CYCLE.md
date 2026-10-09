# Authentication & Token Lifecycle Logic Flow

## User Login & IP-Scoped ABAC Lockout Flowchart
This flowchart details credential verification, Argon2id check, IP+Username brute-force lockout, and initial session creation:

```mermaid
flowchart TD
    A[Client Submits Credentials & IP] --> B[Fetch User by Username from DB]
    B -->|User Not Found| C[Raise 401 Unauthorized]
    B -->|User Found| D{Check Redis IP+Username Lockout<br/>failed_login_block:ip:username}
    
    D -->|Locked Out in Redis| E[Raise 401 Unauthorized: Generic Error]
    D -->|Not Locked Out| F{Check banned_until_time in DB}
    
    F -->|Active Admin Ban| G[Raise 403 Forbidden: Account Inactive]
    F -->|Ban Expired| H[Lift Ban: status = ACTIVE<br/>Commit to DB]
    F -->|No Ban Set| I{Check user.status == ACTIVE}
    H --> I
    
    I -->|Status != ACTIVE| J[Raise 403 Forbidden: Account Inactive]
    I -->|Status == ACTIVE| K[Verify Password via Argon2id]
    
    K -->|Password Invalid| L[Increment failed_login_count:ip:username in Redis]
    L --> M{attempts >= 5 in 15 mins?}
    M -->|Yes| N[Set failed_login_block:ip:username in Redis<br/>TTL = 15 Mins]
    M -->|No| O[Raise 401 Unauthorized: Invalid Credentials]
    N --> O
    
    K -->|Password Valid| P[Clear failed_login state in Redis for ip:username]
    P --> Q[Check User Profile Completion]
    Q --> R{Check Active Session in DB<br/>get_active_session_by_user_id}
    
    R -->|No Active Session| S[Generate Access JWT & Refresh JWT]
    R -->|Active Session Exists| T{now - last_active_at <= 30 mins?<br/>SESSION_IDLE_TIMEOUT_SEC}
    
    T -->|Yes: Recent / Active Terminal| U[Raise 409 Conflict: ACTIVE_SESSION_EXISTS<br/>Generic Message: Active session in progress]
    T -->|No: Stale / Abandoned Session| V[Auto-retire Old Session in DB & Redis<br/>Set is_active = False]
    V --> S
    
    S --> W[Compute SHA-256 Hashes of Both Tokens]
    W --> X[Save Session in PostgreSQL session.sessions]
    X --> Y[Cache Session Payload in Redis<br/>sessions:sid:user:uid]
    Y --> Z[Return Auth Payload & Set HTTP-Only Cookies]
```

---