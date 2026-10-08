# Refresh Token Rotation (RTR) & Fast-Path DB Sync Flowchart
This diagram illustrates the single-authoritative Redis validation path, token rotation, theft detection, and non-blocking background DB sync:

```mermaid
flowchart TD
    A[Client Requests Token Refresh] --> B[Extract refresh_token from Cookies]
    B -->|Cookie Missing| C[Raise 401 Unauthorized]
    B -->|Cookie Present| D[Decode & Verify Refresh JWT Signature]
    
    D -->|Signature Invalid / Expired| E[Raise 401 Unauthorized: Invalid Session]
    D -->|Valid JWT Claims| F[Fetch Redis Cache Key<br/>sessions:sid:user:uid]
    
    F -->|Cache Hit & Session Active| G{Compare Incoming Hash vs<br/>cached refresh_token_hash}
    G -->|Hash Mismatch Token Reuse Detected| H[Immediate Revocation:<br/>Set DB is_active=False<br/>Delete Redis Cache]
    H --> I[Raise 401 Unauthorized: Session Revoked]
    
    G -->|Hash Match Success| J[Generate Rotated Access JWT + Refresh JWT]
    J --> K[Update Redis Cache with New Hashes<br/>access_token_hash & refresh_token_hash]
    K --> L[Dispatch Non-Blocking Background Task<br/>_sync_session_rotation_db]
    L --> M[Return 200 OK & Set New HTTP-Only Cookies]
    
    F -->|Cache Miss / Eviction| N[Fallback to PostgreSQL DB Query]
    N -->|DB Session Inactive or Missing| H
    N -->|DB Session Active & Hash Match| O[Rotate Tokens, Update DB immediately,<br/>Re-warm Redis Cache]
    O --> M
```

---
