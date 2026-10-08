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
    Q --> R[Generate Access JWT & Refresh JWT]
    R --> S[Compute SHA-256 Hashes of Both Tokens]
    S --> T[Save Session in PostgreSQL session.sessions]
    T --> U[Cache Session Payload in Redis<br/>sessions:sid:user:uid]
    U --> V[Return Auth Payload & Set HTTP-Only Cookies]
```

---