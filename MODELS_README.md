# Models Management Feature

This document describes the new Models management feature added to ChassisUI.

## Overview

The Models feature allows users to create, edit, and delete AI models with multiple endpoints and configurable weights for load balancing.

## Features

### Model Management
- **Create Models**: Add new AI models with name, description, and optional photo URL
- **Edit Models**: Modify existing model details and endpoints
- **Delete Models**: Remove models and their associated endpoints
- **View Models**: See all your models in a grid layout

### Endpoint Management
- **Multiple Endpoints**: Each model can have multiple endpoints
- **Weight Configuration**: Set weights for load balancing (e.g., 2:1 ratio)
- **Active/Inactive Status**: Enable or disable individual endpoints
- **URL Configuration**: Set the API endpoint URL for each model

## Database Schema

### Models Table
```sql
CREATE TABLE models (
    model_id uuid DEFAULT gen_random_uuid() NOT NULL,
    name text NOT NULL,
    owner_user_id uuid,
    description text,
    created_at timestamp without time zone DEFAULT now(),
    photo text
);
```

### Model Endpoints Table
```sql
CREATE TABLE model_endpoints (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    model_id uuid,
    url text NOT NULL,
    is_active boolean DEFAULT true,
    weight integer DEFAULT 1
);
```

## Usage

### Accessing Models
1. Navigate to the chat interface
2. Click the user menu (👨) in the top-right corner
3. Select "Models" from the dropdown menu
4. You'll be taken to the Models management page

### Creating a Model
1. Click the "+ Add Model" button
2. Fill in the model details:
   - **Name**: Required model name
   - **Description**: Optional description
   - **Photo URL**: Optional image URL
3. Add endpoints:
   - **URL**: The API endpoint URL
   - **Active**: Whether the endpoint is active
   - **Weight**: Load balancing weight (1-10)
4. Click "Save Model"

### Editing a Model
1. Click the "Edit" button on any model card
2. Modify the model details and endpoints
3. Click "Save Model"

### Deleting a Model
1. Click the "Delete" button on any model card
2. Confirm the deletion in the popup dialog
3. The model and all its endpoints will be removed

## API Endpoints

### GET /api/models
Get all models for the current user

### POST /api/models
Create a new model with endpoints

### GET /api/models/{model_id}
Get a specific model by ID

### PUT /api/models/{model_id}
Update a model and its endpoints

### DELETE /api/models/{model_id}
Delete a model and its endpoints

### GET /models
Serve the models management page

## Weight System

The weight system allows for load balancing between multiple endpoints:

- **Weight 1**: Normal priority
- **Weight 2**: Twice as likely to be used as weight 1
- **Weight 3**: Three times as likely to be used as weight 1
- And so on...

Example: If you have two endpoints with weights 2 and 1, the first endpoint will be used twice as often as the second endpoint.

## Security

- Models are user-specific (owner_user_id)
- Users can only access their own models
- All API endpoints require authentication
- Input validation and sanitization are implemented

## UI Features

- **Responsive Design**: Works on desktop and mobile
- **Dark Theme**: Consistent with the chat interface
- **Real-time Updates**: Changes are reflected immediately
- **Error Handling**: User-friendly error messages
- **Loading States**: Visual feedback during operations

## File Structure

```
static/
├── models.html      # Models page HTML
├── models.js        # Models page JavaScript
└── chat.html        # Updated with Models button

routes.py            # Updated with models API endpoints
```

## Future Enhancements

- Model testing functionality
- Endpoint health monitoring
- Usage statistics
- Model sharing between users
- Advanced load balancing algorithms 