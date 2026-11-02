# AI Chat Feature

## Overview

The AI Chat feature enables real-time infrastructure investigation using cloud-based AI models. Users can ask questions about their infrastructure, and the system will:

1. Gather relevant context from Prometheus metrics
2. Retrieve relevant documents from Qdrant vector database
3. Use the cloud AI router (Gemini → Groq → OpenRouter) to generate evidence-based findings
4. Persist the conversation for future reference

## Architecture

### Backend Components

#### Investigation Endpoint
- **POST** `/api/v1/conversations/{conversation_id}/investigate`
- Creates user message
- Runs AI investigation with full context
- Adds assistant response to conversation
- Returns investigation response with routing metadata

#### Services
- `AIInvestigator`: Orchestrates investigation workflow
- `CloudAIRouter`: Manages provider fallback (Gemini → Groq → OpenRouter)
- `PrometheusClient`: Retrieves infrastructure metrics
- `DocumentService`: Searches Qdrant for relevant documentation
- `ConversationService`: Persists messages and conversations

#### Data Flow
```
User Question
    ↓
Create User Message
    ↓
Gather Prometheus Metrics (CPU, memory, disk, network)
    ↓
Retrieve Qdrant Documents (based on user context)
    ↓
Cloud AI Router (free-tier only, exhaustive fallback)
    ↓
Generate Findings
    ↓
Create Assistant Message
    ↓
Return Investigation Response
```

### Frontend Components

#### Chat Page (`frontend/src/pages/chat-page.tsx`)
- Conversation list sidebar
- Message display area
- Message input with loading states
- Error handling and retry

#### Conversation Service (`frontend/src/services/conversations.ts`)
- `investigate()`: Calls investigation endpoint
- Returns `InvestigationResponse` with findings, evidence, routing metadata

#### UI States
1. **Idle**: Ready for user input
2. **Investigating**: Shows animated loading indicator
3. **Success**: Displays assistant response in conversation
4. **Error**: Shows error message with retry option

## Cloud AI Router

The investigation uses a free-tier cloud AI router with exhaustive fallback:

### Provider Priority
1. **Gemini** (Google AI Studio)
   - All available free models attempted
   - Discovery via `/models` API
   
2. **Groq** 
   - All available free models attempted
   - Discovery via `/models` API
   
3. **OpenRouter**
   - All free models (verified $0.00 pricing) attempted
   - Discovery via `/models` API

### Features
- **Zero Cost Enforcement**: Only free models used
- **Exhaustive Fallback**: All models in registry attempted before provider failure
- **No Artificial Limits**: No max attempts per provider
- **Circuit Breaker**: Stops retrying provider after 999,999 consecutive failures
- **Metrics**: Prometheus metrics for routing decisions and latency

## Context Gathering

### Prometheus Metrics
The system gathers relevant metrics based on question keywords:

- **CPU metrics**: `cpu`, `processor`, `usage`
- **Memory metrics**: `memory`, `ram`, `oom`
- **Disk metrics**: `disk`, `storage`, `filesystem`
- **Network metrics**: `network`, `bandwidth`, `traffic`, `connection`

Metrics collected:
- `cpu_usage_percent`
- `memory_usage_percent` 
- `disk_usage_percent`
- Network throughput (bytes/sec)

### Qdrant Document Retrieval
- Searches vector database for relevant documentation
- Uses cloud embedding service (Google text-embedding-004)
- Returns top relevant chunks with similarity scores
- Currently skipped without user context (future enhancement)

## Security

### Authentication
- All endpoints require valid session token
- CSRF protection on state-changing operations
- Session expiration enforced

### Authorization
- Users can only access their own conversations
- Investigation results scoped to user's infrastructure access

### Rate Limiting
- Investigation endpoint subject to standard rate limits
- Cloud AI providers have their own rate limiting
- Circuit breaker prevents excessive failed requests

## Testing

### Backend Tests
```bash
cd backend
python -m pytest tests/test_auth_and_conversations.py::test_investigation_creates_assistant_response -v
```

Verifies:
- User message created
- Investigation runs successfully
- Assistant message created with findings
- Investigation response returned with metadata

### Integration Testing
```bash
# Start services
docker compose -f deployment/docker-compose.yml up -d

# Test investigation
curl -X POST http://localhost:8000/api/v1/conversations/{id}/investigate \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: {token}" \
  -b "kibolens_session={session}" \
  -d '{"content": "What is the current CPU usage?"}'
```

## Configuration

### Environment Variables

```bash
# Cloud AI Providers (at least one required)
GEMINI_API_KEY=your-key-here
GROQ_API_KEY=your-key-here
OPENROUTER_API_KEY=your-key-here

# Prometheus (required for metrics)
PROMETHEUS_URL=http://prometheus:9090
PROMETHEUS_TIMEOUT_SECONDS=10

# Qdrant (optional for document retrieval)
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=
QDRANT_COLLECTION_NAME=kibolens_docs
```

### Model Configuration
- No explicit model configuration required
- All free models discovered dynamically
- Provider priority: Gemini → Groq → OpenRouter
- Retry configuration in `backend/app/core/config.py`

## Monitoring

### Metrics Exported
- `ai_router_requests_total`: Total requests by provider, model, status
- `ai_router_latency_seconds`: Latency histogram by provider, model
- `ai_router_errors_total`: Errors by provider, error_type
- `investigation_requests_total`: Total investigations
- `investigation_duration_seconds`: Investigation duration

### Logs
```python
# Investigation start
logger.info("Starting investigation", extra={"question": question, "user_id": user_id})

# Provider attempts
logger.info("Attempting provider", extra={"provider": "gemini", "model": model_id})

# Investigation complete
logger.info("Investigation complete", extra={
    "provider": result["routing_metadata"]["provider"],
    "model": result["routing_metadata"]["model"],
    "duration_ms": duration
})
```

## Future Enhancements

1. **Streaming Responses**: WebSocket-based streaming for real-time updates
2. **Multi-turn Context**: Use full conversation history for follow-up questions
3. **Incident Integration**: Automatic investigation when incidents are created
4. **Custom Prompts**: User-configurable investigation prompts
5. **Export Conversations**: Export as markdown, PDF, or JSON
6. **Shared Conversations**: Share investigations with team members
7. **Suggested Questions**: AI-generated follow-up questions based on findings

## Troubleshooting

### "Investigation failed" Error
- Check that at least one cloud AI provider key is configured
- Verify Prometheus is accessible at configured URL
- Check backend logs for detailed error messages
- Verify cloud provider API keys are valid

### No Assistant Response
- Check that investigation endpoint is being called (not message endpoint)
- Verify findings are being generated by AI provider
- Check that assistant message is being created in database

### Empty Findings
- Verify Prometheus metrics are available
- Check that question contains relevant keywords
- Review cloud AI router logs for provider errors
- Confirm at least one free model is available

### Routing Metadata Missing
- Normal for local Ollama deployments
- Cloud router always includes routing metadata
- Check `ai_router_available` in health endpoint
