# Analytics System Documentation

## Overview

The analytics system tracks model usage to provide trending models, user history, and recommendations. This enables users to discover popular models and helps model creators get paid based on usage.

## Database Schema

### Model Usage Analytics Table

```sql
CREATE TABLE model_usage_analytics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id UUID REFERENCES models(model_id),
    user_id UUID REFERENCES users(user_id),
    conversation_id UUID REFERENCES conversations(conversation_id),
    usage_type TEXT NOT NULL, -- 'conversation_start', 'message_sent', 'tokens_used', etc.
    usage_count INTEGER DEFAULT 1,
    tokens_used INTEGER, -- if you track token usage
    created_at TIMESTAMP DEFAULT NOW(),
    session_duration INTEGER -- in seconds, if you track how long conversations last
);
```

## API Endpoints

### 1. Track Usage
**POST** `/api/analytics/usage`

Track when a model is used for analytics and payment purposes.

**Request Body:**
```json
{
    "model_id": "uuid",
    "conversation_id": "uuid",
    "usage_type": "conversation_start|message_sent|tokens_used",
    "usage_count": 1,
    "tokens_used": 150,
    "session_duration": 1800
}
```

### 2. Get Trending Models
**GET** `/api/analytics/trending?time_period=week&limit=10`

Get models trending based on recent usage.

**Parameters:**
- `time_period`: "day", "week", "month" (default: "week")
- `limit`: Number of models to return (default: 10)

**Response:**
```json
[
    {
        "model_id": "uuid",
        "name": "Model Name",
        "description": "Model description",
        "photo": "photo_url",
        "created_at": "2024-01-15T10:30:00",
        "usage_count": 150,
        "unique_users": 45
    }
]
```

### 3. Get User History
**GET** `/api/analytics/user-history`

Get models the current user has used before.

**Response:**
```json
[
    {
        "model_id": "uuid",
        "name": "Model Name",
        "description": "Model description",
        "photo": "photo_url",
        "created_at": "2024-01-15T10:30:00",
        "last_used": "2024-01-20T14:30:00"
    }
]
```

### 4. Get Recommended Models
**GET** `/api/analytics/recommended?limit=10`

Get recommended models for the current user (new models + popular models they haven't used).

**Response:**
```json
[
    {
        "model_id": "uuid",
        "name": "Model Name",
        "description": "Model description",
        "photo": "photo_url",
        "created_at": "2024-01-15T10:30:00",
        "usage_count": 25
    }
]
```

### 5. Get Model Suggestions
**GET** `/api/analytics/model-suggestions`

Get all model suggestions for new chat creation (trending, used, new, recommended).

**Response:**
```json
{
    "trending": [...],
    "used": [...],
    "new": [...]
}
```

## Frontend Integration

### Model Selection Modal

When creating a new chat, users see a modal with four categories:

1. **🔥 Trending** - Models with high usage in the last week
2. **📚 Recently Used** - Models the user has used before
3. **🆕 New Models** - Models created in the last 30 days
4. **💡 Recommended** - New models + popular models user hasn't tried

### Usage Tracking

Usage is automatically tracked when:
- A new conversation is created with a model (`conversation_start`)
- A message is sent in a conversation with a model (`message_sent`)

## Payment Integration

The analytics system provides the foundation for payment processing:

1. **Usage Tracking** - Every model usage is recorded with timestamps
2. **Revenue Calculation** - Can calculate revenue based on usage metrics
3. **Payment Periods** - Support for daily, weekly, monthly payment cycles
4. **Model Owner Attribution** - Track which user owns each model

## Testing

Run the test script to verify analytics functionality:

```bash
python test_analytics.py
```

This will:
1. Create test models and conversations
2. Add usage analytics data
3. Test all analytics queries
4. Clean up test data

## Implementation Notes

### Automatic Usage Tracking

Usage is automatically tracked in these scenarios:

1. **Conversation Creation**: When `POST /api/conversations` is called with a `model_id`
2. **Message Streaming**: When `POST /api/conversations/{id}/messages/stream` is called for a conversation with a model

### Performance Considerations

- Analytics queries use proper indexing on `created_at`, `model_id`, and `user_id`
- Trending calculations are cached and updated periodically
- Large datasets can be aggregated into summary tables for better performance

### Security

- All analytics endpoints require authentication
- Users can only see their own usage history
- Model information is publicly viewable (for discovery) but usage data is private

## Future Enhancements

1. **Advanced Recommendations** - AI-powered model recommendations based on user behavior
2. **Usage Analytics Dashboard** - For model creators to view their model performance
3. **Revenue Sharing** - Automatic payment processing based on usage
4. **A/B Testing** - Test different recommendation algorithms
5. **Real-time Analytics** - Live usage statistics and trending 