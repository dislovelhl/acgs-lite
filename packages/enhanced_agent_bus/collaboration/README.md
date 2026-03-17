# Real-time Collaboration Module for ACGS-2

**Constitutional Hash**: `cdd01ef066bc6cf2`

This module enables multiple users to simultaneously edit policies and workflows with presence tracking, cursor synchronization, and live updates.

## Features

- **Real-time Presence**: Track active users, their status (active/idle/typing/away), and cursors
- **Operational Transform**: Conflict-free concurrent editing using OT algorithms
- **Comments & Chat**: Inline comments with @mentions and real-time chat
- **Permission Control**: Role-based access (read/write/admin) with document locking
- **Audit Trail**: All collaborative actions logged for compliance

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    COLLABORATION SERVICE                    │
├─────────────────────────────────────────────────────────────┤
│  Socket.io Server                                           │
│  ├── Room Management (per document)                        │
│  ├── Presence Tracking                                     │
│  ├── Cursor Position Sync                                  │
│  ├── Operational Transform                                 │
│  └── History/Undo                                          │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Backend

```python
from packages.enhanced_agent_bus.collaboration import CollaborationServer

# Initialize server
server = CollaborationServer(
    config=CollaborationConfig(max_users_per_document=50),
    redis_client=redis_client,  # Optional, for persistence
    auth_validator=validate_token,  # JWT validation
)

await server.initialize()

# Mount to FastAPI/Starlette app
app.mount("/collaboration", server.get_asgi_app())
```

### Frontend

```tsx
import {
  CollaborationProvider,
  PresenceBar,
  CursorOverlay,
} from "@/components/collaboration";

function PolicyEditor({ policyId }) {
  return (
    <CollaborationProvider
      serverUrl="ws://localhost:8001"
      authToken={userToken}
    >
      <PresenceBar documentName="Policy #123" />
      <PolicyEditorContent policyId={policyId} />
      <CursorOverlay containerRef={editorRef} />
    </CollaborationProvider>
  );
}
```

## Components

### Backend

| Component        | Purpose                                 |
| ---------------- | --------------------------------------- |
| `server.py`      | Socket.io server with event handlers    |
| `presence.py`    | User presence and cursor tracking       |
| `sync_engine.py` | Operational Transform and document sync |
| `permissions.py` | RBAC and document locking               |
| `models.py`      | Pydantic models for all data structures |

### Frontend

| Component               | Purpose                      |
| ----------------------- | ---------------------------- |
| `CollaborationProvider` | Socket connection management |
| `PresenceBar`           | Active users avatar stack    |
| `CursorOverlay`         | Render remote cursors        |
| `CommentThreads`        | Inline comments sidebar      |
| `ActivityFeed`          | Edit history and rollback    |

## Socket Events

### Client → Server

| Event              | Payload                       | Description             |
| ------------------ | ----------------------------- | ----------------------- |
| `join-document`    | `{ documentId, userId, ... }` | Join a document session |
| `leave-document`   | -                             | Leave current session   |
| `cursor-move`      | `{ position }`                | Update cursor position  |
| `edit-operation`   | `{ operation }`               | Send edit operation     |
| `typing-indicator` | `{ is_typing }`               | Typing status           |
| `chat-message`     | `{ text, mentions }`          | Send chat message       |
| `add-comment`      | `{ text, position }`          | Add inline comment      |

### Server → Client

| Event             | Payload                   | Description         |
| ----------------- | ------------------------- | ------------------- |
| `user-joined`     | `{ userId, name, color }` | User joined         |
| `user-left`       | `{ userId, client_id }`   | User left           |
| `cursor-update`   | `{ userId, position }`    | Cursor moved        |
| `document-update` | `{ operation, version }`  | Document changed    |
| `presence-update` | `{ users }`               | Full presence state |
| `chat-message`    | `{ message }`             | New chat message    |

## Operational Transform

The sync engine uses Operational Transform to handle concurrent edits:

```python
# Two users insert at same position
op1 = EditOperation(type='insert', position=5, value='X')
op2 = EditOperation(type='insert', position=5, value='Y')

# Transform so both can be applied
t1, t2 = ot.transform_operations(op1, op2)
# Result: t1 at 5, t2 at 6
```

## Permissions

```python
# Permission levels
UserPermissions.READ   # View only
UserPermissions.WRITE  # Edit content
UserPermissions.ADMIN  # Lock, manage permissions

# Document locking
await permissions.lock_document(doc_id, user_id, session)
await permissions.unlock_document(doc_id, user_id, session)
```

## Testing

```bash
# Run collaboration tests
pytest src/core/enhanced_agent_bus/collaboration/tests/ -v

# Run specific test file
pytest tests/test_sync_engine.py -v
pytest tests/test_presence.py -v
pytest tests/test_permissions.py -v
```

## Configuration

```python
CollaborationConfig(
    max_users_per_document=50,
    cursor_sync_interval_ms=50,
    operation_batch_size=10,
    history_retention_hours=24,
    enable_chat=True,
    enable_comments=True,
    enable_presence=True,
    idle_timeout_seconds=300,
    away_timeout_seconds=600,
)
```

## Security Considerations

- WebSocket connections require JWT authentication
- Tenant isolation enforced at session level
- All operations validated against user permissions
- Rate limiting on cursor updates and edits
- Audit logging of all collaborative actions

## Performance Targets

- 10+ concurrent users per document
- < 100ms latency for cursor sync
- < 500ms latency for document updates
- Conflict resolution without data loss
- Graceful handling of disconnections

## Constitutional Compliance

- All collaborative edits logged to audit trail
- MACI role separation maintained
- Constitutional hash validation on all changes
- Version history immutable
