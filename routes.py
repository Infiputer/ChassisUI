import json
import bcrypt
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Response, Request, Depends, Query, BackgroundTasks
from fastapi.responses import FileResponse
from schemas import UserSignup, UserLogin, MessageCreate
from auth import get_current_user_id, create_tokens
from database import get_db_pool
import jwt
from config import JWT_SECRET, JWT_ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS
from fastapi import Body
import uuid
import httpx
from fastapi.responses import StreamingResponse
import asyncio
from typing import Dict, Optional, List, Set
import weakref

router = APIRouter()

# Global configuration
DATABASE_SAVE_INTERVAL_SECONDS = 10.0  # How often to save to database during streaming

# Global state to track ongoing streaming sessions
streaming_sessions: Dict[str, dict] = {}

# Global state to track background processing tasks
background_tasks_running: Dict[str, bool] = {}

# Shared Stream Manager for efficient model connection reuse
class SharedStreamManager:
    def __init__(self):
        self.active_streams: Dict[str, 'SharedStream'] = {}
        self._cleanup_task = None
    
    def get_or_create_stream(self, conversation_id: str, messages_arr: list, user_id: str, pool) -> 'SharedStream':
        """Get existing stream or create new one for conversation"""
        if conversation_id in self.active_streams:
            stream = self.active_streams[conversation_id]
            if stream.is_active():
                print(f"Reusing existing stream for conversation {conversation_id}")
                return stream
            else:
                # Clean up dead stream
                del self.active_streams[conversation_id]
        
        # Create new shared stream
        stream = SharedStream(conversation_id, messages_arr, user_id, pool)
        self.active_streams[conversation_id] = stream
        print(f"Created new shared stream for conversation {conversation_id}")
        return stream
    
    def remove_stream(self, conversation_id: str):
        """Remove stream from active streams"""
        if conversation_id in self.active_streams:
            del self.active_streams[conversation_id]
            print(f"Removed shared stream for conversation {conversation_id}")
    
    def cleanup_dead_streams(self):
        """Clean up any dead streams"""
        dead_conversations = []
        for conv_id, stream in self.active_streams.items():
            if not stream.is_active():
                dead_conversations.append(conv_id)
        
        for conv_id in dead_conversations:
            del self.active_streams[conv_id]
            print(f"Cleaned up dead stream for conversation {conv_id}")

# Global shared stream manager
shared_stream_manager = SharedStreamManager()

class SharedStream:
    def __init__(self, conversation_id: str, messages_arr: list, user_id: str, pool):
        self.conversation_id = conversation_id
        self.messages_arr = messages_arr
        self.user_id = user_id
        self.pool = pool
        self.consumers: Set['StreamConsumer'] = set()
        self.tokens: List[dict] = []
        self.is_complete = False
        self.is_error = False
        self.error_message = None
        self._stream_task = None
        self._lock = asyncio.Lock()
        
    async def start_streaming(self):
        """Start the actual model streaming in background"""
        if self._stream_task is None:
            self._stream_task = asyncio.create_task(self._stream_from_model())
    
    async def _stream_from_model(self):
        """Stream from model endpoint and distribute to all consumers"""
        try:
            model_url = "http://localhost:8001/api/chat"
            model_payload = {
                "model": "Test",
                "messages": self.messages_arr,
                "stream": True,
                "generate_title": True
            }
            
            print(f"SharedStream: Starting model request for conversation {self.conversation_id}")
            
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", model_url, json=model_payload) as resp:
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                                await self._distribute_token(data)
                            except json.JSONDecodeError:
                                continue
            
            self.is_complete = True
            print(f"SharedStream: Completed streaming for conversation {self.conversation_id}")
            
        except Exception as e:
            self.is_error = True
            self.error_message = str(e)
            print(f"SharedStream: Error in streaming for conversation {self.conversation_id}: {e}")
        finally:
            # Notify all consumers that stream is done
            await self._notify_consumers_complete()
    
    async def _distribute_token(self, data: dict):
        """Distribute token to all active consumers"""
        async with self._lock:
            self.tokens.append(data)
            
            # Notify all consumers
            consumers_to_remove = set()
            for consumer in self.consumers:
                try:
                    await consumer.receive_token(data)
                except Exception as e:
                    print(f"Error delivering token to consumer: {e}")
                    consumers_to_remove.add(consumer)
            
            # Remove dead consumers
            for consumer in consumers_to_remove:
                self.consumers.discard(consumer)
    
    async def _notify_consumers_complete(self):
        """Notify all consumers that streaming is complete"""
        async with self._lock:
            consumers_to_remove = set()
            for consumer in self.consumers:
                try:
                    await consumer.stream_complete()
                except Exception as e:
                    print(f"Error notifying consumer of completion: {e}")
                    consumers_to_remove.add(consumer)
            
            for consumer in consumers_to_remove:
                self.consumers.discard(consumer)
    
    def add_consumer(self, consumer: 'StreamConsumer'):
        """Add a consumer to this stream"""
        self.consumers.add(consumer)
        print(f"Added consumer to shared stream for conversation {self.conversation_id}")
    
    def remove_consumer(self, consumer: 'StreamConsumer'):
        """Remove a consumer from this stream"""
        self.consumers.discard(consumer)
        print(f"Removed consumer from shared stream for conversation {self.conversation_id}")
        
        # If no more consumers and stream is complete, clean up
        if not self.consumers and self.is_complete:
            shared_stream_manager.remove_stream(self.conversation_id)
    
    def is_active(self) -> bool:
        """Check if stream is still active"""
        return self._stream_task is not None and not self._stream_task.done()
    
    def get_tokens_since(self, index: int) -> List[dict]:
        """Get all tokens since a given index"""
        return self.tokens[index:]

class StreamConsumer:
    def __init__(self, stream: SharedStream, start_from_index: int = 0):
        self.stream = stream
        self.start_index = start_from_index
        self.current_index = start_from_index
        self.is_active = True
    
    async def receive_token(self, data: dict):
        """Receive a token from the shared stream"""
        if not self.is_active:
            return
        
        # Skip tokens we've already seen
        if self.current_index < len(self.stream.tokens) - 1:
            self.current_index += 1
            return
        
        # This is a new token for us
        self.current_index += 1
        await self._process_token(data)
    
    async def _process_token(self, data: dict):
        """Process a token - to be overridden by subclasses"""
        pass
    
    async def stream_complete(self):
        """Called when the shared stream is complete"""
        self.is_active = False
        await self._on_complete()
    
    async def _on_complete(self):
        """Called when stream is complete - to be overridden by subclasses"""
        pass
    
    def deactivate(self):
        """Deactivate this consumer"""
        self.is_active = False
        self.stream.remove_consumer(self)

class FrontendStreamConsumer(StreamConsumer):
    """Consumer for frontend streaming - yields tokens to client"""
    def __init__(self, stream: SharedStream, start_from_index: int = 0):
        super().__init__(stream, start_from_index)
        self.token_queue = asyncio.Queue()
        self.assistant_reply = ""
        self.title_sent = False
        self.last_save_time = asyncio.get_event_loop().time()
        self.assistant_msg_id = None
        self.conversation_id = None
        self.user_msg_id = None
        self.pool = None
        self.idx = 0
    
    def setup_db_info(self, assistant_msg_id: str, conversation_id: str, user_msg_id: str, pool, idx: int):
        """Setup database information for periodic saves"""
        self.assistant_msg_id = assistant_msg_id
        self.conversation_id = conversation_id
        self.user_msg_id = user_msg_id
        self.pool = pool
        self.idx = idx
    
    async def _process_token(self, data: dict):
        """Process token and add to queue for frontend"""
        # Check for title message
        if data.get("message", {}).get("title"):
            title = data["message"]["title"]
            print(f"FrontendConsumer: Received title: {title}")
            await self.token_queue.put(data)
            return
        
        # Check for done message
        if data.get("done", False):
            print(f"FrontendConsumer: Received done message")
            await self.token_queue.put(data)
            return
        
        # Regular token
        token = data.get("message", {}).get("content", "")
        if token:
            self.assistant_reply += token
            await self.token_queue.put(token)
            
            # Periodic save every 10 seconds
            current_time = asyncio.get_event_loop().time()
            if current_time - self.last_save_time > DATABASE_SAVE_INTERVAL_SECONDS:
                await self._save_to_database()
                self.last_save_time = current_time
    
    async def _save_to_database(self):
        """Save current response to database"""
        if not self.pool or not self.assistant_msg_id:
            return
        
        print(f"FrontendConsumer: Saving {len(self.assistant_reply)} characters to database")
        async with self.pool.acquire() as conn:
            # Check if message already exists
            existing = await conn.fetchval(
                "SELECT message_id FROM messages WHERE message_id = $1", self.assistant_msg_id
            )
            if existing:
                # Update existing message
                await conn.execute(
                    "UPDATE messages SET content = $1 WHERE message_id = $2",
                    self.assistant_reply, self.assistant_msg_id
                )
                print(f"FrontendConsumer: Updated existing message: {self.assistant_msg_id}")
            else:
                # Insert new message
                await conn.execute(
                    "INSERT INTO messages (message_id, conversation_id, parent_message_id, role, content, order_index) VALUES ($1, $2, $3, $4, $5, $6)",
                    self.assistant_msg_id, self.conversation_id, self.user_msg_id, "assistant", self.assistant_reply, self.idx + 1
                )
                await conn.execute(
                    "UPDATE conversations SET current_leaf_message_id = $1 WHERE conversation_id = $2",
                    self.assistant_msg_id, self.conversation_id
                )
                print(f"FrontendConsumer: Inserted new message: {self.assistant_msg_id}")
    
    async def get_next_token(self):
        """Get next token for frontend streaming"""
        try:
            return await asyncio.wait_for(self.token_queue.get(), timeout=30.0)
        except asyncio.TimeoutError:
            return None
    
    async def _on_complete(self):
        """Called when stream is complete"""
        # Final save to database
        await self._save_to_database()
        print(f"FrontendConsumer: Stream complete, final save done")

class BackgroundStreamConsumer(StreamConsumer):
    """Consumer for background processing - saves to database without frontend streaming"""
    def __init__(self, stream: SharedStream, start_from_index: int = 0, partial_response: str = ""):
        super().__init__(stream, start_from_index)
        self.assistant_reply = partial_response
        self.last_save_time = asyncio.get_event_loop().time()
        self.save_interval = 2.0
        self.assistant_msg_id = None
        self.conversation_id = None
        self.user_id = None
        self.pool = None
        self.tokens_processed = 0
        self.new_tokens_count = 0
    
    def setup_db_info(self, assistant_msg_id: str, conversation_id: str, user_id: str, pool):
        """Setup database information"""
        self.assistant_msg_id = assistant_msg_id
        self.conversation_id = conversation_id
        self.user_id = user_id
        self.pool = pool
    
    async def _process_token(self, data: dict):
        """Process token for background processing"""
        # Check for title message
        if data.get("message", {}).get("title"):
            title = data["message"]["title"]
            print(f"BackgroundConsumer: Received title: {title}")
            # Save the title to the database
            await save_title_to_db(self.conversation_id, title, self.user_id, self.pool)
            return
        
        # Check for done message
        if data.get("done", False):
            print(f"BackgroundConsumer: Received done message")
            return
        
        # Regular token
        token = data.get("message", {}).get("content", "")
        if token:
            # Skip tokens that were already processed in the partial response
            if self.tokens_processed < len(self.assistant_reply):
                # Skip this token as it was already processed
                self.tokens_processed += len(token)
                print(f"BackgroundConsumer: Skipping token (already processed): {token[:20]}...")
                return
            else:
                # Add new tokens to the response
                self.assistant_reply += token
                self.new_tokens_count += 1
                print(f"BackgroundConsumer: Added new token #{self.new_tokens_count}: {token[:20]}...")
                
                # Adaptive save interval: more frequent saves early on, then less frequent
                current_time = asyncio.get_event_loop().time()
                if current_time - self.last_save_time > self.save_interval:
                    await self._save_to_database()
                    self.last_save_time = current_time
                    
                    # Gradually increase save interval to reduce database load
                    if self.save_interval < DATABASE_SAVE_INTERVAL_SECONDS:
                        self.save_interval = min(self.save_interval * 1.5, DATABASE_SAVE_INTERVAL_SECONDS)
                        print(f"BackgroundConsumer: Increased save interval to {self.save_interval}s")
    
    async def _save_to_database(self):
        """Save current response to database"""
        if not self.pool or not self.assistant_msg_id:
            return
        
        print(f"BackgroundConsumer: Saving {len(self.assistant_reply)} characters to database")
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE messages SET content = $1 WHERE message_id = $2",
                self.assistant_reply, self.assistant_msg_id
            )
            print(f"BackgroundConsumer: Updated message: {self.assistant_msg_id}")
    
    async def _on_complete(self):
        """Called when stream is complete"""
        print(f"BackgroundConsumer: Stream complete, total new tokens: {self.new_tokens_count}")
        
        # Save the complete response to the database
        print(f"BackgroundConsumer: Saving complete response to DB: {self.assistant_reply[:100]}...")
        try:
            async with self.pool.acquire() as conn:
                # Clean up any background processing indicators from the response
                clean_response = self.assistant_reply
                clean_response = clean_response.replace("*[Response will be completed in background]*", "")
                clean_response = clean_response.replace("*[Response completed in background]*", "")
                clean_response = clean_response.replace("Response will be completed in background", "")
                clean_response = clean_response.replace("Response completed in background", "")
                clean_response = clean_response.strip()
                
                # Update the existing assistant message with the clean complete response
                await conn.execute(
                    "UPDATE messages SET content = $1 WHERE message_id = $2",
                    clean_response, self.assistant_msg_id
                )
                
                # Update current leaf to point to the assistant message
                await conn.execute(
                    "UPDATE conversations SET current_leaf_message_id = $1 WHERE conversation_id = $2",
                    self.assistant_msg_id, self.conversation_id
                )
                
                print(f"BackgroundConsumer: Successfully saved clean complete response to database")
        except Exception as e:
            print(f"BackgroundConsumer: Error saving to database: {e}")
        finally:
            # Mark background processing as complete
            background_tasks_running[self.conversation_id] = False
            # Clean up the tracking entry
            if self.conversation_id in background_tasks_running:
                del background_tasks_running[self.conversation_id]
            print(f"BackgroundConsumer: Background task completed for conversation {self.conversation_id}")

class ResumeStreamConsumer(StreamConsumer):
    """Consumer for resume streaming - yields new tokens to reconnected client"""
    def __init__(self, stream: SharedStream, start_from_index: int = 0, partial_response: str = ""):
        super().__init__(stream, start_from_index)
        self.token_queue = asyncio.Queue()
        self.assistant_reply = partial_response
        self.tokens_processed = 0
        self.new_tokens_count = 0
        self.last_assistant_msg_id = None
        self.pool = None
        self.title_sent = False
    
    def setup_db_info(self, last_assistant_msg_id: str, pool):
        """Setup database information"""
        self.last_assistant_msg_id = last_assistant_msg_id
        self.pool = pool
    
    async def _process_token(self, data: dict):
        """Process token for resume streaming"""
        # Check for title message
        if data.get("message", {}).get("title"):
            title = data["message"]["title"]
            print(f"ResumeConsumer: Received title: {title}")
            # Send title in proper format
            title_response = {
                "model": "Test",
                "created_at": datetime.now().isoformat() + "Z",
                "message": {"title": title},
                "done": False
            }
            await self.token_queue.put(json.dumps(title_response))
            return
        
        # Check for done message
        if data.get("done", False):
            print(f"ResumeConsumer: Received done message")
            # Send done message in proper format
            done_response = {
                "model": "Test",
                "created_at": datetime.now().isoformat() + "Z",
                "done": True
            }
            await self.token_queue.put(json.dumps(done_response))
            return
        
        # Regular token
        token = data.get("message", {}).get("content", "")
        if token:
            # Skip tokens that were already processed in the partial response
            if self.tokens_processed < len(self.assistant_reply):
                # Skip this token as it was already processed
                self.tokens_processed += len(token)
                print(f"ResumeConsumer: Skipping token (already processed): {token[:20]}...")
                return
            else:
                # Add new tokens to the response
                self.assistant_reply += token
                self.new_tokens_count += 1
                print(f"ResumeConsumer: Added new token #{self.new_tokens_count}: {token[:20]}...")
                
                # Send token to frontend in proper format (just the token content as JSON string)
                await self.token_queue.put(json.dumps(token))
                
                # Save to database periodically
                if self.new_tokens_count % 50 == 0:  # Save every 50 tokens
                    await self._save_to_database()
    
    async def _save_to_database(self):
        """Save current response to database"""
        if not self.pool or not self.last_assistant_msg_id:
            return
        
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE messages SET content = $1 WHERE message_id = $2",
                self.assistant_reply, self.last_assistant_msg_id
            )
            print(f"ResumeConsumer: Updated message: {self.last_assistant_msg_id}")
    
    async def get_next_token(self):
        """Get next token for resume streaming"""
        try:
            # Check if stream is complete and we have no more tokens
            if self.stream.is_complete and self.token_queue.empty():
                print("ResumeConsumer: Stream is complete and no more tokens")
                return None
            
            # Wait for next token with shorter timeout
            return await asyncio.wait_for(self.token_queue.get(), timeout=5.0)
        except asyncio.TimeoutError:
            # If timeout and stream is complete, we're done
            if self.stream.is_complete:
                print("ResumeConsumer: Timeout and stream complete - ending")
                return None
            # If timeout but stream still active, continue waiting
            print("ResumeConsumer: Timeout but stream still active - continuing")
            return await self.get_next_token()
    
    async def stream_complete(self):
        """Called when the shared stream is complete"""
        print("ResumeConsumer: Stream complete notification received")
        # Put a sentinel value to signal completion
        await self.token_queue.put("__STREAM_COMPLETE__")
    
    async def _on_complete(self):
        """Called when stream is complete"""
        # Save the complete response to the database
        print(f"ResumeConsumer: Saving complete response to DB: {self.assistant_reply[:100]}...")
        try:
            async with self.pool.acquire() as conn:
                await conn.execute(
                    "UPDATE messages SET content = $1 WHERE message_id = $2",
                    self.assistant_reply, self.last_assistant_msg_id
                )
                print(f"ResumeConsumer: Successfully saved complete response to database")
        except Exception as e:
            print(f"ResumeConsumer: Error saving to database: {e}")

# Helper function to save title to database
async def save_title_to_db(conversation_id: str, title: str, user_id: str, pool):
    """Save a generated title to the database"""
    try:
        async with pool.acquire() as conn:
            # Verify user owns this conversation
            owner = await conn.fetchval(
                "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
            )
            if str(owner) != str(user_id):
                print(f"DEBUG: User {user_id} does not own conversation {conversation_id}")
                return False
            
            # Update the conversation title
            await conn.execute(
                "UPDATE conversations SET title = $1 WHERE conversation_id = $2",
                title, conversation_id
            )
            print(f"DEBUG: Successfully saved title '{title}' to conversation {conversation_id}")
            return True
    except Exception as e:
        print(f"DEBUG: Error saving title to database: {e}")
        return False

# Background task to continue processing model response
async def continue_model_response_background(
    conversation_id: str, 
    user_msg_id: str, 
    assistant_msg_id: str, 
    messages_arr: list, 
    user_id: str, 
    pool, 
    partial_response: str = "",
    captured_data: list = None
):
    """Continue processing the model response in the background after client disconnects"""
    print(f"=== BACKGROUND TASK STARTED ===")
    print(f"Starting background task to continue model response for conversation {conversation_id}")
    print(f"Partial response length: {len(partial_response)}")
    print(f"Captured data chunks: {len(captured_data) if captured_data else 0}")
    
    # Mark this conversation as having background processing
    background_tasks_running[conversation_id] = True
    print(f"Marked conversation {conversation_id} as having background processing")
    
    # Use shared stream manager instead of making new model call
    shared_stream = shared_stream_manager.get_or_create_stream(
        conversation_id, messages_arr, user_id, pool
    )
    
    # Create background consumer
    background_consumer = BackgroundStreamConsumer(shared_stream, partial_response=partial_response)
    background_consumer.setup_db_info(assistant_msg_id, conversation_id, user_id, pool)
    
    # Add consumer to stream
    shared_stream.add_consumer(background_consumer)
    
    # Start streaming if not already started
    await shared_stream.start_streaming()
    
    # Wait for stream to complete
    while not shared_stream.is_complete and not shared_stream.is_error:
        await asyncio.sleep(0.1)
    
    print(f"=== BACKGROUND TASK FINISHED ===")

# List all conversations for the current user
@router.get("/api/conversations")
async def list_conversations(user_id: str = Depends(get_current_user_id), pool=Depends(get_db_pool)):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT conversation_id, title, created_at FROM conversations WHERE user_id = $1 ORDER BY created_at DESC",
            user_id
        )
        return [dict(row) for row in rows]

# Create a new conversation
@router.post("/api/conversations")
async def create_conversation(
    data: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    title = data.get("title", "New chat")
    model_id = data.get("model_id")
    
    conversation_id = str(uuid.uuid4())
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO conversations (conversation_id, user_id, title, model_id) VALUES ($1, $2, $3, $4)",
            conversation_id, user_id, title, model_id
        )
        
        # Track usage analytics if model_id is provided
        if model_id:
            await conn.execute("""
                INSERT INTO model_usage_analytics 
                (model_id, user_id, conversation_id, usage_type, usage_count)
                VALUES ($1, $2, $3, $4, $5)
            """, model_id, user_id, conversation_id, "conversation_start", 1)
    
    return {"conversation_id": conversation_id, "title": title, "model_id": model_id}

# Rename conversation
@router.put("/api/conversations/{conversation_id}/title")
async def rename_conversation(
    conversation_id: str,
    new_title: str = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        await conn.execute(
            "UPDATE conversations SET title = $1 WHERE conversation_id = $2",
            new_title, conversation_id
        )
    return {"ok": True, "title": new_title}

# Update conversation model
@router.put("/api/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    data: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Update model_id if provided
        if "model_id" in data:
            await conn.execute(
                "UPDATE conversations SET model_id = $1 WHERE conversation_id = $2",
                data["model_id"], conversation_id
            )
        
        # Update title if provided
        if "title" in data:
            await conn.execute(
                "UPDATE conversations SET title = $1 WHERE conversation_id = $2",
                data["title"], conversation_id
            )
    
    return {"ok": True}

# Get conversation meta (current leaf)
@router.get("/api/conversations/{conversation_id}/meta")
async def get_conversation_meta(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT current_leaf_message_id, model_id FROM conversations WHERE conversation_id = $1 AND user_id = $2",
            conversation_id, user_id
        )
        if not row:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return dict(row)

# Set current leaf
@router.put("/api/conversations/{conversation_id}/leaf")
async def set_current_leaf(
    conversation_id: str,
    data: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    message_id = data.get("message_id")
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        await conn.execute(
            "UPDATE conversations SET current_leaf_message_id = $1 WHERE conversation_id = $2",
            message_id, conversation_id
        )
    return {"ok": True}

# Get messages along the path from root to leaf, with user_children for branching
@router.get("/api/conversations/{conversation_id}/messages")
async def get_branch_messages(
    conversation_id: str,
    leaf_id: str = Query(None),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        
        if not leaf_id:
            leaf_id = await conn.fetchval(
                "SELECT current_leaf_message_id FROM conversations WHERE conversation_id = $1", conversation_id
            )
        
        print(f"Fetching messages for conversation {conversation_id}, leaf_id: {leaf_id}")
        
        # Get all messages in the conversation
        rows = await conn.fetch(
            "SELECT message_id, parent_message_id, role, content, order_index FROM messages WHERE conversation_id = $1 ORDER BY order_index",
            conversation_id
        )
        
        print(f"Found {len(rows)} total messages in conversation")
        
        if not rows:
            return []
            
        msg_map = {row["message_id"]: dict(row) for row in rows}
        
        # Build the path from root to current leaf
        path = []
        cur = msg_map.get(leaf_id)
        while cur:
            path.insert(0, cur)
            cur = msg_map.get(cur["parent_message_id"])
        
        print(f"Built path with {len(path)} messages")
        for i, msg in enumerate(path):
            print(f"  Message {i}: id={msg['message_id']}, role={msg['role']}, content={msg['content'][:50]}...")
        
        # Add user_children to each message in the path
        # This should include ALL user messages that are children of each message, not just those in the current path
        for msg in path:
            msg["user_children"] = [
                dict(child) for child in rows
                if child["parent_message_id"] == msg["message_id"] and child["role"] == "user"
            ]
            print(f"  Message {msg['message_id']} ({msg['role']}) has {len(msg['user_children'])} user_children: {[c['message_id'] for c in msg['user_children']]}")
            
            # Add assistant_children to user messages for branching
            if msg["role"] == "user":
                msg["assistant_children"] = [
                    dict(child) for child in rows
                    if child["parent_message_id"] == msg["message_id"] and child["role"] == "assistant"
                ]
                print(f"  Message {msg['message_id']} (user) has {len(msg['assistant_children'])} assistant_children: {[c['message_id'] for c in msg['assistant_children']]}")
                
                # Add sibling information for user messages
                # Find all user messages that have the same parent as this message
                msg["siblings"] = [
                    dict(sibling) for sibling in rows
                    if sibling["parent_message_id"] == msg["parent_message_id"] and 
                       sibling["role"] == "user" and 
                       sibling["message_id"] != msg["message_id"]
                ]
                print(f"  Message {msg['message_id']} (user) has {len(msg['siblings'])} siblings: {[s['message_id'] for s in msg['siblings']]}")
        
        return path

# Add a user message and generate assistant reply (streaming)
@router.post("/api/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: str,
    data: MessageCreate,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    prompt = data.prompt
    parent_message_id = getattr(data, "parent_message_id", None)
    
    # Store these values for use in the generator
    user_msg_id = str(uuid.uuid4())
    assistant_msg_id = str(uuid.uuid4())
    conversation_context = ""
    idx = 0
    messages_arr = []  # Build messages array here
    
    async with pool.acquire() as conn:
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Get the model_id for this conversation
        model_id = await conn.fetchval(
            "SELECT model_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        
        idx = await conn.fetchval(
            "SELECT COALESCE(MAX(order_index), 0) + 1 FROM messages WHERE conversation_id = $1", conversation_id
        )
        
        # If no parent_message_id provided, use the current leaf (last assistant message)
        if not parent_message_id:
            parent_message_id = await conn.fetchval(
                "SELECT current_leaf_message_id FROM conversations WHERE conversation_id = $1", conversation_id
            )
        
        # Insert the user message
        await conn.execute(
            "INSERT INTO messages (message_id, conversation_id, parent_message_id, role, content, order_index) VALUES ($1, $2, $3, $4, $5, $6)",
            user_msg_id, conversation_id, parent_message_id, "user", prompt, idx
        )
        
        # Update current leaf to point to the user message immediately
        await conn.execute(
            "UPDATE conversations SET current_leaf_message_id = $1 WHERE conversation_id = $2",
            user_msg_id, conversation_id
        )
        print(f"DEBUG: Updated current leaf to user message: {user_msg_id}")

        # Track usage analytics if model_id is available
        if model_id:
            await conn.execute("""
                INSERT INTO model_usage_analytics 
                (model_id, user_id, conversation_id, usage_type, usage_count)
                VALUES ($1, $2, $3, $4, $5)
            """, model_id, user_id, conversation_id, "message_sent", 1)

        # Build conversation context and messages array for Ollama
        if parent_message_id:
            # Get all messages in the conversation
            rows = await conn.fetch(
                "SELECT message_id, parent_message_id, role, content, order_index FROM messages WHERE conversation_id = $1 ORDER BY order_index",
                conversation_id
            )
            msg_map = {row["message_id"]: dict(row) for row in rows}
            
            # Build path from root to parent
            context_path = []
            cur = msg_map.get(parent_message_id)
            while cur:
                context_path.insert(0, cur)
                cur = msg_map.get(cur["parent_message_id"])
            
            # Build context string
            for msg in context_path:
                conversation_context += f"{msg['role'].title()}: {msg['content']}\n"
            
            # Build messages array for Ollama
            for msg in context_path:
                messages_arr.append({"role": msg["role"], "content": msg["content"]})
        
        # Add the new prompt
        conversation_context += f"User: {prompt}\n"
        messages_arr.append({"role": "user", "content": prompt})

    async def event_generator():
        # Use shared stream manager instead of direct model calls
        shared_stream = shared_stream_manager.get_or_create_stream(
            conversation_id, messages_arr, user_id, pool
        )
        
        # Create frontend consumer
        frontend_consumer = FrontendStreamConsumer(shared_stream)
        frontend_consumer.setup_db_info(assistant_msg_id, conversation_id, user_msg_id, pool, idx)
        
        # Add consumer to stream
        shared_stream.add_consumer(frontend_consumer)
        
        # Start streaming if not already started
        await shared_stream.start_streaming()
        
        # Mark background processing as active
        background_tasks_running[conversation_id] = True
        
        try:
            # Stream tokens to frontend
            while True:
                token = await frontend_consumer.get_next_token()
                if token is None:
                    # Timeout or stream ended
                    break
                
                # Send token to frontend
                if isinstance(token, dict):
                    # Title or done message
                    yield f"data: {json.dumps(token)}\n\n"
                    if token.get("done", False):
                        break
                else:
                    # Regular token
                    yield f"data: {json.dumps(token)}\n\n"
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            print(f"Frontend streaming error: {e}")
            # Check if this is a client disconnect
            error_str = str(e).lower()
            if (isinstance(e, (ConnectionResetError, BrokenPipeError, ConnectionError)) or 
                "connectionreseterror" in str(type(e)).lower() or 
                "brokenpipeerror" in str(type(e)).lower() or 
                "connectionerror" in str(type(e)).lower() or
                "connection aborted" in error_str or
                "connection reset" in error_str or
                "broken pipe" in error_str or
                "client disconnected" in error_str or
                "remote end closed" in error_str or
                "end of stream" in error_str or
                "stream closed" in error_str):
                print("Client disconnected - background processing will continue")
                # Don't add interruption message since background processing continues
            else:
                # Other types of interruptions
                if frontend_consumer.assistant_reply:
                    frontend_consumer.assistant_reply += "\n\n*[Response stopped by user]*"
                yield "data: [INTERRUPTED]\n\n"
        finally:
            # Deactivate frontend consumer
            frontend_consumer.deactivate()
            
            # If stream is complete and no more consumers, clean up
            if shared_stream.is_complete and not shared_stream.consumers:
                shared_stream_manager.remove_stream(conversation_id)

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Edit a user message: create a new branch (child) and new assistant reply
@router.put("/api/messages/{message_id}/stream")
async def edit_message_stream(
    message_id: str,
    background_tasks: BackgroundTasks,
    new_content: str = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    # Validate message_id
    if not message_id or message_id == "undefined":
        raise HTTPException(status_code=400, detail="Invalid message_id")
    
    print(f"Edit request: message_id={message_id}, new_content={new_content[:50]}...")
    
    # Store these values for use in the generator
    new_user_msg_id = str(uuid.uuid4())
    new_assistant_msg_id = str(uuid.uuid4())
    conversation_id = ""
    conversation_context = ""
    idx = 0
    messages_arr = []  # Build messages array here
    
    # Find the original message and build context
    async with pool.acquire() as conn:
        orig = await conn.fetchrow(
            "SELECT conversation_id, role, parent_message_id FROM messages WHERE message_id = $1", message_id
        )
        if not orig:
            raise HTTPException(status_code=404, detail=f"Message not found: {message_id}")
        if orig["role"] != "user":
            raise HTTPException(status_code=400, detail="Can only edit user messages")
        conversation_id = orig["conversation_id"]
        
        print(f"Found original message in conversation: {conversation_id}")
        
        # Build conversation context up to the parent of the edited message
        rows = await conn.fetch(
            "SELECT message_id, parent_message_id, role, content, order_index FROM messages WHERE conversation_id = $1 ORDER BY order_index",
            conversation_id
        )
        msg_map = {row["message_id"]: dict(row) for row in rows}
        
        # Build path from root to the parent of the edited message (not including the edited message)
        context_path = []
        parent_id = orig["parent_message_id"]
        cur = msg_map.get(parent_id)
        while cur:
            context_path.insert(0, cur)
            cur = msg_map.get(cur["parent_message_id"])
        
        print(f"Built context path with {len(context_path)} messages (up to parent of edited message)")
        
        # Build the conversation context for the LLM
        for msg in context_path:
            conversation_context += f"{msg['role'].title()}: {msg['content']}\n"
        
        # Build messages array for Ollama
        for msg in context_path:
            messages_arr.append({"role": msg["role"], "content": msg["content"]})
        
        # Add the new content
        conversation_context += f"User: {new_content}\n"
        messages_arr.append({"role": "user", "content": new_content})
        
        # The new message should be a child of the edited message's parent, not the edited message itself
        parent_message_id = orig["parent_message_id"]
        
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        idx = await conn.fetchval(
            "SELECT COALESCE(MAX(order_index), 0) + 1 FROM messages WHERE conversation_id = $1", conversation_id
        )
        
        # Insert the new user message
        await conn.execute(
            "INSERT INTO messages (message_id, conversation_id, parent_message_id, role, content, order_index) VALUES ($1, $2, $3, $4, $5, $6)",
            new_user_msg_id, conversation_id, parent_message_id, "user", new_content, idx
        )
        
        print(f"Inserted new user message: {new_user_msg_id}")

    async def event_generator():
        model_url = "http://localhost:8001/api/chat"
        model_payload = {
            "model": "Test",
            "messages": messages_arr,
            "stream": True,
            "generate_title": True
        }
        assistant_reply = ""
        was_interrupted = False
        client_disconnected = False
        captured_data = []  # Capture all streaming data for background processing
        background_task_started = False
        last_save_time = asyncio.get_event_loop().time()
        
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", model_url, json=model_payload) as resp:
                    buffer = ""
                    async for chunk in resp.aiter_text():
                        buffer += chunk
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            if not line.strip():
                                continue
                            try:
                                data = json.loads(line)
                                # Capture all data for potential background processing
                                captured_data.append(data)
                                print(f"DEBUG: Received data from model endpoint: {data}")
                                
                                # Check for title message
                                if data.get("message", {}).get("title"):
                                    title = data["message"]["title"]
                                    print(f"DEBUG: Received title message: {title}")
                                    # Forward the title message to frontend
                                    yield f"data: {json.dumps(data)}\n\n"
                                    continue
                                
                                # Check for done message
                                if data.get("done", False):
                                    print(f"DEBUG: Received done message from model endpoint")
                                    yield f"data: {json.dumps(data)}\n\n"
                                    break
                                
                                # Regular token
                                token = data.get("message", {}).get("content", "")
                                if token:
                                    assistant_reply += token
                                    yield f"data: {json.dumps(token)}\n\n"
                                    
                                    # Periodic save every 10 seconds
                                    current_time = asyncio.get_event_loop().time()
                                    if current_time - last_save_time > DATABASE_SAVE_INTERVAL_SECONDS:  # Use global variable
                                        print(f"Periodic save: Saving {len(assistant_reply)} characters to database")
                                        async with pool.acquire() as conn:
                                            # Check if message already exists
                                            existing = await conn.fetchval(
                                                "SELECT message_id FROM messages WHERE message_id = $1", new_assistant_msg_id
                                            )
                                            if existing:
                                                # Update existing message
                                                await conn.execute(
                                                    "UPDATE messages SET content = $1 WHERE message_id = $2",
                                                    assistant_reply, new_assistant_msg_id
                                                )
                                                print(f"Updated existing message: {new_assistant_msg_id}")
                                            else:
                                                # Insert new message
                                                await conn.execute(
                                                    "INSERT INTO messages (message_id, conversation_id, parent_message_id, role, content, order_index) VALUES ($1, $2, $3, $4, $5, $6)",
                                                    new_assistant_msg_id, conversation_id, new_user_msg_id, "assistant", assistant_reply, idx + 1
                                                )
                                                await conn.execute(
                                                    "UPDATE conversations SET current_leaf_message_id = $1 WHERE conversation_id = $2",
                                                    new_assistant_msg_id, conversation_id
                                                )
                                                print(f"Inserted new message: {new_assistant_msg_id}")
                                        last_save_time = current_time
                                    
                                    # Start background task after we have some content (in case client disconnects)
                                    if len(assistant_reply) > 50 and not background_task_started:
                                        print(f"Starting background task after {len(assistant_reply)} characters")
                                        background_task_started = True
                                        
                                        # Save current partial response
                                        async with pool.acquire() as conn:
                                            await conn.execute(
                                                "INSERT INTO messages (message_id, conversation_id, parent_message_id, role, content, order_index) VALUES ($1, $2, $3, $4, $5, $6)",
                                                new_assistant_msg_id, conversation_id, new_user_msg_id, "assistant", assistant_reply, idx + 1
                                            )
                                            await conn.execute(
                                                "UPDATE conversations SET current_leaf_message_id = $1 WHERE conversation_id = $2",
                                                new_assistant_msg_id, conversation_id
                                            )
                                            print(f"Saved partial response to database: {new_assistant_msg_id}")
                                        
                                        # Start background task
                                        try:
                                            background_tasks.add_task(
                                                continue_model_response_background,
                                                conversation_id, 
                                                new_user_msg_id, 
                                                new_assistant_msg_id, 
                                                messages_arr, 
                                                user_id, 
                                                pool, 
                                                assistant_reply,
                                                captured_data
                                            )
                                            print(f"Background task started for conversation {conversation_id}")
                                        except Exception as bg_error:
                                            print(f"Error starting background task: {bg_error}")
                            except Exception as e:
                                print(f"DEBUG: Error parsing line: {e}, line: {line}")
                                continue
                    yield "data: [DONE]\n\n"
        except Exception as e:
            # Handle stream interruption
            was_interrupted = True
            print(f"Stream interrupted with exception: {type(e).__name__}: {str(e)}")
            print(f"Exception type: {type(e)}")
            print(f"Exception args: {e.args}")
            
            # Check if this is a client disconnect (common when tab is closed)
            error_str = str(e).lower()
            if (isinstance(e, (ConnectionResetError, BrokenPipeError, ConnectionError)) or 
                "connectionreseterror" in str(type(e)).lower() or 
                "brokenpipeerror" in str(type(e)).lower() or 
                "connectionerror" in str(type(e)).lower() or
                "connection aborted" in error_str or
                "connection reset" in error_str or
                "broken pipe" in error_str or
                "client disconnected" in error_str or
                "remote end closed" in error_str or
                "end of stream" in error_str or
                "stream closed" in error_str):
                print("Client disconnected (likely tab closed) - background task should continue")
                client_disconnected = True
                # Don't add interruption message since background task will continue
            else:
                # Other types of interruptions
                print(f"Other type of interruption: {type(e).__name__}")
                if assistant_reply:
                    assistant_reply += "\n\n*[Response stopped by user]*"
                yield "data: [INTERRUPTED]\n\n"
        
        # If client disconnected and we haven't started background task yet, start it now
        if client_disconnected and assistant_reply and not background_task_started:
            print(f"Client disconnected for conversation {conversation_id}, starting background task...")
            print(f"Partial response length: {len(assistant_reply)} characters")
            print(f"Captured {len(captured_data)} data chunks for background processing")
            
            # First save the partial response to the database
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO messages (message_id, conversation_id, parent_message_id, role, content, order_index) VALUES ($1, $2, $3, $4, $5, $6)",
                    new_assistant_msg_id, conversation_id, new_user_msg_id, "assistant", assistant_reply, idx + 1
                )
                await conn.execute(
                    "UPDATE conversations SET current_leaf_message_id = $1 WHERE conversation_id = $2",
                    new_assistant_msg_id, conversation_id
                )
                print(f"Saved partial response to database: {new_assistant_msg_id}")
            
            # Add the background task to continue processing the captured data
            try:
                background_tasks.add_task(
                    continue_model_response_background,
                    conversation_id, 
                    new_user_msg_id, 
                    new_assistant_msg_id, 
                    messages_arr, 
                    user_id, 
                    pool, 
                    assistant_reply,
                    captured_data
                )
                print(f"Background task successfully added for conversation {conversation_id}")
            except Exception as bg_error:
                print(f"Error adding background task: {bg_error}")
            
            # Send a message indicating the response will be completed in background
            yield "data: [CONTINUING_IN_BACKGROUND]\n\n"
            return
        
        # After streaming (complete or interrupted), save the assistant reply to the DB and update current_leaf
        if not background_task_started:  # Only save if background task hasn't already saved it
            print(f"Saving assistant reply to DB: {assistant_reply[:100]}...")
            async with pool.acquire() as conn:
                await conn.execute(
                    "INSERT INTO messages (message_id, conversation_id, parent_message_id, role, content, order_index) VALUES ($1, $2, $3, $4, $5, $6)",
                    new_assistant_msg_id, conversation_id, new_user_msg_id, "assistant", assistant_reply, idx + 1
                )
                await conn.execute(
                    "UPDATE conversations SET current_leaf_message_id = $1 WHERE conversation_id = $2",
                    new_assistant_msg_id, conversation_id
                )
                
                print(f"Inserted assistant message: {new_assistant_msg_id}")
                print(f"Updated current leaf to: {new_assistant_msg_id}")
            print(f"DB write complete, sending [SAVED] event")
            yield "data: [SAVED]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

# Find the leaf message of a branch
@router.get("/api/messages/{message_id}/leaf")
async def get_branch_leaf(
    message_id: str,
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    async with pool.acquire() as conn:
        # First verify the message exists and user has access
        msg = await conn.fetchrow(
            "SELECT m.conversation_id, c.user_id FROM messages m JOIN conversations c ON m.conversation_id = c.conversation_id WHERE m.message_id = $1",
            message_id
        )
        if not msg or str(msg["user_id"]) != str(user_id):
            raise HTTPException(status_code=404, detail="Message not found")
        
        # Find the leaf by walking down the conversation tree
        leaf_id = message_id
        while True:
            # Check if this message has any children
            child = await conn.fetchrow(
                "SELECT message_id FROM messages WHERE parent_message_id = $1 ORDER BY order_index DESC LIMIT 1",
                leaf_id
            )
            if not child:
                break
            leaf_id = child["message_id"]
        
        return {"leaf_message_id": leaf_id}

# Save partial response when streaming fails
@router.post("/api/conversations/{conversation_id}/partial-response")
async def save_partial_response(
    conversation_id: str,
    data: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    content = data.get("content", "")
    if not content:
        raise HTTPException(status_code=400, detail="No content provided")
    
    async with pool.acquire() as conn:
        # Verify user owns the conversation
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Get the last user message to use as parent
        last_user_msg = await conn.fetchrow(
            "SELECT message_id FROM messages WHERE conversation_id = $1 AND role = 'user' ORDER BY order_index DESC LIMIT 1",
            conversation_id
        )
        if not last_user_msg:
            raise HTTPException(status_code=404, detail="No user message found")
        
        # Get next order index
        idx = await conn.fetchval(
            "SELECT COALESCE(MAX(order_index), 0) + 1 FROM messages WHERE conversation_id = $1", conversation_id
        )
        
        # Create assistant message ID
        assistant_msg_id = str(uuid.uuid4())
        
        # Insert the partial response
        await conn.execute(
            "INSERT INTO messages (message_id, conversation_id, parent_message_id, role, content, order_index) VALUES ($1, $2, $3, $4, $5, $6)",
            assistant_msg_id, conversation_id, last_user_msg["message_id"], "assistant", content, idx
        )
        
        # Update current leaf
        await conn.execute(
            "UPDATE conversations SET current_leaf_message_id = $1 WHERE conversation_id = $2",
            assistant_msg_id, conversation_id
        )
        
        print(f"Saved partial response: {assistant_msg_id}")
        return {"message_id": assistant_msg_id}

# Save generated title
@router.post("/api/conversations/{conversation_id}/save-title")
async def save_generated_title(
    conversation_id: str,
    data: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    title = data.get("title", "")
    print(f"DEBUG: Save title request - conversation_id: {conversation_id}, title: {title}")
    
    if not title:
        print(f"DEBUG: Title is empty, returning error")
        raise HTTPException(status_code=400, detail="Title is required")
    
    async with pool.acquire() as conn:
        # Verify user owns this conversation
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            print(f"DEBUG: User {user_id} does not own conversation {conversation_id}")
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Update the conversation title
        await conn.execute(
            "UPDATE conversations SET title = $1 WHERE conversation_id = $2",
            title, conversation_id
        )
        print(f"DEBUG: Successfully saved title '{title}' to conversation {conversation_id}")
    
    return {"ok": True, "title": title}

# Check if a response is still being processed in background
@router.get("/api/conversations/{conversation_id}/processing-status")
async def get_processing_status(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Check if there are any incomplete responses being processed"""
    async with pool.acquire() as conn:
        # Verify user owns this conversation
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Check if background task is running
        if background_tasks_running.get(conversation_id, False):
            return {
                "processing": True, 
                "message": "Response is being completed in background",
                "can_resume": True,
                "status": "background_processing"
            }
        
        # Check if the last message is incomplete (contains background processing indicator)
        last_message = await conn.fetchrow(
            "SELECT content, message_id FROM messages WHERE conversation_id = $1 ORDER BY order_index DESC LIMIT 1",
            conversation_id
        )
        
        if last_message:
            content = last_message["content"]
            # Check if the message contains background processing indicators
            has_background_indicators = (
                "Response will be completed in background" in content or 
                "Response completed in background" in content or
                "*[Response will be completed in background]*" in content or
                "*[Response completed in background]*" in content
            )
            
            # If it has background indicators, check if the response looks complete
            if has_background_indicators:
                # Check if the response is substantial (more than just the indicator)
                clean_content = content.replace("*[Response will be completed in background]*", "").replace("*[Response completed in background]*", "").strip()
                
                # If the response is substantial (more than 100 characters), consider it complete
                if len(clean_content) > 100:
                    print(f"DEBUG: Background processing appears complete - response has {len(clean_content)} characters")
                    return {
                        "processing": False, 
                        "message": "Background processing completed",
                        "can_resume": False,
                        "status": "completed"
                    }
                else:
                    return {
                        "processing": True, 
                        "message": "Response is being completed in background",
                        "can_resume": True,
                        "status": "background_processing",
                        "last_message_id": last_message["message_id"]
                    }
        
        return {
            "processing": False, 
            "message": "No background processing",
            "can_resume": False,
            "status": "idle"
        }

# Resume streaming for a conversation with background processing
@router.post("/api/conversations/{conversation_id}/resume-streaming")
async def resume_streaming(
    conversation_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Resume streaming for a conversation that has background processing"""
    async with pool.acquire() as conn:
        # Verify user owns this conversation
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Get the last assistant message that might be incomplete
        last_assistant_msg = await conn.fetchrow(
            "SELECT message_id, content, parent_message_id FROM messages WHERE conversation_id = $1 AND role = 'assistant' ORDER BY order_index DESC LIMIT 1",
            conversation_id
        )
        
        if not last_assistant_msg:
            raise HTTPException(status_code=404, detail="No assistant message found")
        
        # Check if this message indicates background processing
        if not ("Response will be completed in background" in last_assistant_msg["content"] or 
                "Response completed in background" in last_assistant_msg["content"]):
            raise HTTPException(status_code=400, detail="No background processing to resume")
        
        # Get the parent user message
        parent_user_msg = await conn.fetchrow(
            "SELECT message_id, content FROM messages WHERE message_id = $1", 
            last_assistant_msg["parent_message_id"]
        )
        
        if not parent_user_msg:
            raise HTTPException(status_code=404, detail="Parent user message not found")
        
        # Build the conversation context up to the parent user message
        rows = await conn.fetch(
            "SELECT message_id, parent_message_id, role, content, order_index FROM messages WHERE conversation_id = $1 ORDER BY order_index",
            conversation_id
        )
        msg_map = {row["message_id"]: dict(row) for row in rows}
        
        # Build path from root to the parent user message
        context_path = []
        cur = msg_map.get(parent_user_msg["message_id"])
        while cur:
            context_path.insert(0, cur)
            cur = msg_map.get(cur["parent_message_id"])
        
        # Build messages array for the model
        messages_arr = []
        for msg in context_path:
            messages_arr.append({"role": msg["role"], "content": msg["content"]})
        
        # Add the user message that triggered the response
        messages_arr.append({"role": "user", "content": parent_user_msg["content"]})
        
        print(f"Resuming streaming for conversation {conversation_id}")
        print(f"Messages array: {len(messages_arr)} messages")
        
        # Start a new background task to continue the response
        try:
            background_tasks.add_task(
                continue_model_response_background,
                conversation_id, 
                parent_user_msg["message_id"], 
                last_assistant_msg["message_id"], 
                messages_arr, 
                user_id, 
                pool, 
                last_assistant_msg["content"],
                []  # No captured data for resume
            )
            print(f"Resume background task started for conversation {conversation_id}")
        except Exception as bg_error:
            print(f"Error starting resume background task: {bg_error}")
            raise HTTPException(status_code=500, detail="Failed to resume streaming")
        
        return {
            "resumed": True,
            "message": "Streaming resumed in background",
            "conversation_id": conversation_id
        }

# Resume streaming with real-time updates (much more efficient than polling)
@router.post("/api/conversations/{conversation_id}/resume-stream")
async def resume_stream(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Resume streaming for a conversation that has background processing - returns a real streaming response"""
    async with pool.acquire() as conn:
        # Verify user owns this conversation
        owner = await conn.fetchval(
            "SELECT user_id FROM conversations WHERE conversation_id = $1", conversation_id
        )
        if str(owner) != str(user_id):
            raise HTTPException(status_code=403, detail="Forbidden")
        
        # Check if background processing is actually running
        if not background_tasks_running.get(conversation_id, False):
            print(f"DEBUG: Resume-stream called for conversation {conversation_id} but no background processing is running")
            raise HTTPException(status_code=400, detail="No background processing in progress")
        
        print(f"DEBUG: Resume-stream called for conversation {conversation_id} - background processing is running")
        
        # Get the last assistant message that might be incomplete
        last_assistant_msg = await conn.fetchrow(
            "SELECT message_id, content, parent_message_id FROM messages WHERE conversation_id = $1 AND role = 'assistant' ORDER BY order_index DESC LIMIT 1",
            conversation_id
        )
        
        if not last_assistant_msg:
            raise HTTPException(status_code=404, detail="No assistant message found")
        
        # Get the parent user message
        parent_user_msg = await conn.fetchrow(
            "SELECT message_id, content FROM messages WHERE message_id = $1", 
            last_assistant_msg["parent_message_id"]
        )
        
        if not parent_user_msg:
            raise HTTPException(status_code=404, detail="Parent user message not found")
        
        # Build the conversation context up to the parent user message
        rows = await conn.fetch(
            "SELECT message_id, parent_message_id, role, content, order_index FROM messages WHERE conversation_id = $1 ORDER BY order_index",
            conversation_id
        )
        msg_map = {row["message_id"]: dict(row) for row in rows}
        
        # Build path from root to the parent user message
        context_path = []
        cur = msg_map.get(parent_user_msg["message_id"])
        while cur:
            context_path.insert(0, cur)
            cur = msg_map.get(cur["parent_message_id"])
        
        # Build messages array for the model
        messages_arr = []
        for msg in context_path:
            messages_arr.append({"role": msg["role"], "content": msg["content"]})
        
        # Add the user message that triggered the response
        messages_arr.append({"role": "user", "content": parent_user_msg["content"]})
        
        print(f"Resuming real-time streaming for conversation {conversation_id}")
        print(f"Messages array: {len(messages_arr)} messages")
        
        # Extract the partial response (remove any background processing indicators that might still be there)
        partial_response = last_assistant_msg["content"]
        partial_response = partial_response.replace("*[Response will be completed in background]*", "").strip()
        partial_response = partial_response.replace("*[Response completed in background]*", "").strip()
        partial_response = partial_response.replace("Response will be completed in background", "").strip()
        partial_response = partial_response.replace("Response completed in background", "").strip()

    async def resume_event_generator():
        """Generate streaming events for resumed conversation using shared stream"""
        # Use shared stream manager instead of making new model call
        shared_stream = shared_stream_manager.get_or_create_stream(
            conversation_id, messages_arr, user_id, pool
        )
        
        # Create resume consumer
        resume_consumer = ResumeStreamConsumer(shared_stream, partial_response=partial_response)
        resume_consumer.setup_db_info(last_assistant_msg["message_id"], pool)
        
        # Add consumer to stream
        shared_stream.add_consumer(resume_consumer)
        
        # Start streaming if not already started
        await shared_stream.start_streaming()
        
        try:
            # Stream new tokens to frontend
            while True:
                token = await resume_consumer.get_next_token()
                if token is None:
                    # No more tokens - stream is complete
                    print("Resume streaming: No more tokens, stream complete")
                    break
                
                # Check for sentinel value indicating stream completion
                if token == "__STREAM_COMPLETE__":
                    print("Resume streaming: Received stream complete signal")
                    break
                
                # Send token to frontend
                yield f"data: {token}\n\n"
            
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            print(f"Resume streaming error: {e}")
            yield "data: [ERROR]\n\n"
        finally:
            # Deactivate resume consumer
            resume_consumer.deactivate()
            
            # If stream is complete and no more consumers, clean up
            if shared_stream.is_complete and not shared_stream.consumers:
                shared_stream_manager.remove_stream(conversation_id)

    return StreamingResponse(resume_event_generator(), media_type="text/event-stream")

# Stream the current progress of background processing
@router.get("/api/conversations/{conversation_id}/stream-progress")
async def stream_progress(
    conversation_id: str,
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Stream the current progress of background processing - DEPRECATED: Use resume-stream instead"""
    raise HTTPException(status_code=410, detail="This endpoint is deprecated. Use /resume-stream for real-time streaming.")

# Models API routes
@router.get("/api/models")
async def list_models(
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool),
    search: str = Query(None),
    sort: str = Query("usage", description="Sort by 'usage' or 'created_at'"),
    limit: int = Query(20),
    offset: int = Query(0)
):
    """Get all models owned by the current user, with search and sort support"""
    try:
        async with pool.acquire() as conn:
            base_query = """
                SELECT 
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at,
                    COUNT(mua.id) as usage_count
                FROM models m
                LEFT JOIN model_usage_analytics mua ON m.model_id = mua.model_id
                WHERE m.owner_user_id = $1
            """
            params = [user_id]
            param_idx = 2
            if search:
                base_query += f" AND (m.name ILIKE ${param_idx} OR m.short_description ILIKE ${param_idx} OR m.long_description ILIKE ${param_idx})"
                params.append(f"%{search}%")
                param_idx += 1
            base_query += " GROUP BY m.model_id, m.name, m.short_description, m.long_description, m.created_at"
            if sort == "usage":
                base_query += " ORDER BY usage_count DESC, m.created_at DESC"
            else:
                base_query += " ORDER BY m.created_at DESC"
            base_query += f" LIMIT ${param_idx} OFFSET ${param_idx+1}"
            params.extend([limit, offset])
            models = await conn.fetch(base_query, *params)
            return [
                {
                    'model_id': str(row['model_id']),
                    'name': row['name'],
                    'short_description': row['short_description'],
                    'long_description': row['long_description'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'usage_count': row['usage_count']
                }
                for row in models
            ]
    except Exception as e:
        print(f"Error listing models: {e}")
        raise HTTPException(status_code=500, detail="Failed to list models")

@router.post("/api/models")
async def create_model(
    data: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Create a new model with endpoints"""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Create the model
                model_id = await conn.fetchval("""
                    INSERT INTO models (name, short_description, long_description, owner_user_id)
                    VALUES ($1, $2, $3, $4)
                    RETURNING model_id
                """, data['name'], data.get('short_description'), data.get('long_description'), user_id)
                # Create endpoints (if any)
                for endpoint in data.get('endpoints', []):
                    await conn.execute("""
                        INSERT INTO model_endpoints (model_id, url, is_active, weight)
                        VALUES ($1, $2, $3, $4)
                    """, model_id, endpoint['url'], endpoint['is_active'], endpoint['weight'])
                return {"model_id": str(model_id), "message": "Model created successfully"}
    except Exception as e:
        print(f"Error creating model: {e}")
        raise HTTPException(status_code=500, detail="Failed to create model")

@router.get("/api/models/{model_id}")
async def get_model(
    model_id: str,
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Get a specific model by ID"""
    try:
        async with pool.acquire() as conn:
            model = await conn.fetchrow("""
                SELECT 
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at,
                    m.owner_user_id
                FROM models m
                WHERE m.model_id = $1
            """, model_id)
            if not model:
                raise HTTPException(status_code=404, detail="Model not found")
            endpoints = await conn.fetch("""
                SELECT id, url, is_active, weight
                FROM model_endpoints
                WHERE model_id = $1
                ORDER BY weight DESC
            """, model_id)
            # Get usage count
            usage_count = await conn.fetchval("SELECT COUNT(*) FROM model_usage_analytics WHERE model_id = $1", model_id)
            return {
                'model_id': str(model['model_id']),
                'name': model['name'],
                'short_description': model['short_description'],
                'long_description': model['long_description'],
                'created_at': model['created_at'].isoformat() if model['created_at'] else None,
                'owner_user_id': str(model['owner_user_id']) if model['owner_user_id'] else None,
                'usage_count': usage_count,
                'endpoints': [
                    {
                        'id': str(ep['id']),
                        'url': ep['url'],
                        'is_active': ep['is_active'],
                        'weight': ep['weight']
                    }
                    for ep in endpoints
                ]
            }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting model: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model")

@router.put("/api/models/{model_id}")
async def update_model(
    model_id: str,
    data: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Update a model and its endpoints"""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                owner = await conn.fetchval("""
                    SELECT owner_user_id FROM models WHERE model_id = $1
                """, model_id)
                if not owner or str(owner) != str(user_id):
                    raise HTTPException(status_code=404, detail="Model not found")
                await conn.execute("""
                    UPDATE models 
                    SET name = $1, short_description = $2, long_description = $3
                    WHERE model_id = $4
                """, data['name'], data.get('short_description'), data.get('long_description'), model_id)
                await conn.execute("""
                    DELETE FROM model_endpoints WHERE model_id = $1
                """, model_id)
                for endpoint in data.get('endpoints', []):
                    await conn.execute("""
                        INSERT INTO model_endpoints (model_id, url, is_active, weight)
                        VALUES ($1, $2, $3, $4)
                    """, model_id, endpoint['url'], endpoint['is_active'], endpoint['weight'])
                return {"message": "Model updated successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating model: {e}")
        raise HTTPException(status_code=500, detail="Failed to update model")

@router.delete("/api/models/{model_id}")
async def delete_model(
    model_id: str,
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Delete a model and its endpoints"""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Verify ownership
                owner = await conn.fetchval("""
                    SELECT owner_user_id FROM models WHERE model_id = $1
                """, model_id)
                
                if not owner or str(owner) != str(user_id):
                    raise HTTPException(status_code=404, detail="Model not found")
                
                # Delete endpoints first (due to foreign key constraint)
                await conn.execute("""
                    DELETE FROM model_endpoints WHERE model_id = $1
                """, model_id)
                
                # Delete the model
                await conn.execute("""
                    DELETE FROM models WHERE model_id = $1
                """, model_id)
                
                return {"message": "Model deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting model: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete model")

@router.get("/models")
async def models_page():
    """Serve the models page"""
    return FileResponse("static/models.html")

# Analytics routes
@router.post("/api/analytics/usage")
async def track_model_usage(
    data: dict = Body(...),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Track model usage for analytics"""
    try:
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO model_usage_analytics 
                (model_id, user_id, conversation_id, usage_type, usage_count, tokens_used, session_duration)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
            """, 
            data['model_id'], 
            user_id, 
            data.get('conversation_id'), 
            data['usage_type'], 
            data.get('usage_count', 1),
            data.get('tokens_used'),
            data.get('session_duration')
            )
            return {"message": "Usage tracked successfully"}
    except Exception as e:
        print(f"Error tracking usage: {e}")
        raise HTTPException(status_code=500, detail="Failed to track usage")

@router.get("/api/analytics/trending")
async def get_trending_models(
    time_period: str = Query("week", description="Time period: day, week, month"),
    limit: int = Query(10, description="Number of models to return"),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Get trending models based on recent usage"""
    try:
        async with pool.acquire() as conn:
            # Calculate time filter based on period
            time_filters = {
                "day": "created_at >= NOW() - INTERVAL '1 day'",
                "week": "created_at >= NOW() - INTERVAL '1 week'",
                "month": "created_at >= NOW() - INTERVAL '1 month'"
            }
            time_filter = time_filters.get(time_period, time_filters["week"])
            
            # Get trending models based on usage count
            trending = await conn.fetch(f"""
                SELECT 
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at,
                    COUNT(mua.id) as usage_count,
                    COUNT(DISTINCT mua.user_id) as unique_users
                FROM models m
                LEFT JOIN model_usage_analytics mua ON m.model_id = mua.model_id 
                    AND {time_filter}
                WHERE m.owner_user_id IS NOT NULL
                GROUP BY m.model_id, m.name, m.short_description, m.long_description, m.created_at
                ORDER BY usage_count DESC, unique_users DESC
                LIMIT $1
            """, limit)
            
            return [
                {
                    'model_id': str(row['model_id']),
                    'name': row['name'],
                    'short_description': row['short_description'],
                    'long_description': row['long_description'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'usage_count': row['usage_count'],
                    'unique_users': row['unique_users']
                }
                for row in trending
            ]
    except Exception as e:
        print(f"Error getting trending models: {e}")
        raise HTTPException(status_code=500, detail="Failed to get trending models")

@router.get("/api/analytics/user-history")
async def get_user_model_history(
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Get models the current user has used before"""
    try:
        async with pool.acquire() as conn:
            history = await conn.fetch("""
                SELECT DISTINCT
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at,
                    MAX(mua.created_at) as last_used
                FROM models m
                INNER JOIN model_usage_analytics mua ON m.model_id = mua.model_id
                WHERE mua.user_id = $1
                GROUP BY m.model_id, m.name, m.short_description, m.long_description, m.created_at
                ORDER BY last_used DESC
            """, user_id)
            
            return [
                {
                    'model_id': str(row['model_id']),
                    'name': row['name'],
                    'short_description': row['short_description'],
                    'long_description': row['long_description'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                    'last_used': row['last_used'].isoformat() if row['last_used'] else None
                }
                for row in history
            ]
    except Exception as e:
        print(f"Error getting user history: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user history")

@router.get("/api/analytics/recommended")
async def get_recommended_models(
    limit: int = Query(10, description="Number of models to return"),
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Get recommended models for the current user"""
    try:
        async with pool.acquire() as conn:
            # Get new models (created in last 30 days) that user hasn't used
            new_models = await conn.fetch("""
                SELECT 
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at
                FROM models m
                WHERE m.created_at >= NOW() - INTERVAL '30 days'
                AND m.owner_user_id IS NOT NULL
                AND m.model_id NOT IN (
                    SELECT DISTINCT model_id 
                    FROM model_usage_analytics 
                    WHERE user_id = $1
                )
                ORDER BY m.created_at DESC
                LIMIT $2
            """, user_id, limit)
            
            # Get popular models user hasn't used
            popular_models = await conn.fetch("""
                SELECT 
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at,
                    COUNT(mua.id) as usage_count
                FROM models m
                LEFT JOIN model_usage_analytics mua ON m.model_id = mua.model_id 
                    AND mua.created_at >= NOW() - INTERVAL '1 week'
                WHERE m.owner_user_id IS NOT NULL
                AND m.model_id NOT IN (
                    SELECT DISTINCT model_id 
                    FROM model_usage_analytics 
                    WHERE user_id = $1
                )
                GROUP BY m.model_id, m.name, m.short_description, m.long_description, m.created_at
                HAVING COUNT(mua.id) > 0
                ORDER BY usage_count DESC
                LIMIT $2
            """, user_id, limit)
            
            # Combine and deduplicate
            all_models = {}
            for row in new_models + popular_models:
                model_id = str(row['model_id'])
                if model_id not in all_models:
                    all_models[model_id] = {
                        'model_id': model_id,
                        'name': row['name'],
                        'short_description': row['short_description'],
                        'long_description': row['long_description'],
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'usage_count': getattr(row, 'usage_count', 0)
                    }
            
            return list(all_models.values())[:limit]
    except Exception as e:
        print(f"Error getting recommended models: {e}")
        raise HTTPException(status_code=500, detail="Failed to get recommended models")

@router.get("/api/analytics/model-suggestions")
async def get_model_suggestions(
    user_id: str = Depends(get_current_user_id),
    pool=Depends(get_db_pool)
):
    """Get all model suggestions for new chat creation"""
    try:
        async with pool.acquire() as conn:
            # Get trending models (last week) - show all models with usage, or all models if no usage data
            trending = await conn.fetch("""
                SELECT 
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at,
                    COUNT(mua.id) as usage_count,
                    'trending' as category
                FROM models m
                LEFT JOIN model_usage_analytics mua ON m.model_id = mua.model_id 
                    AND mua.created_at >= NOW() - INTERVAL '1 week'
                WHERE m.owner_user_id IS NOT NULL
                GROUP BY m.model_id, m.name, m.short_description, m.long_description, m.created_at
                ORDER BY usage_count DESC, m.created_at DESC
                LIMIT 5
            """)
            
            # Get user's previously used models
            used = await conn.fetch("""
                SELECT DISTINCT
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at,
                    MAX(mua.created_at) as last_used,
                    'used' as category
                FROM models m
                INNER JOIN model_usage_analytics mua ON m.model_id = mua.model_id
                WHERE mua.user_id = $1
                GROUP BY m.model_id, m.name, m.short_description, m.long_description, m.created_at
                ORDER BY last_used DESC
                LIMIT 5
            """, user_id)
            
            # Get new models user hasn't used (created in last 30 days)
            new = await conn.fetch("""
                SELECT 
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at,
                    'new' as category
                FROM models m
                WHERE m.created_at >= NOW() - INTERVAL '30 days'
                AND m.owner_user_id IS NOT NULL
                AND m.model_id NOT IN (
                    SELECT DISTINCT model_id 
                    FROM model_usage_analytics 
                    WHERE user_id = $1
                )
                ORDER BY m.created_at DESC
                LIMIT 5
            """, user_id)
            
            # Get all available models for recommendations (models user hasn't used)
            all_available = await conn.fetch("""
                SELECT 
                    m.model_id,
                    m.name,
                    m.short_description,
                    m.long_description,
                    m.created_at,
                    COUNT(mua.id) as usage_count,
                    'recommended' as category
                FROM models m
                LEFT JOIN model_usage_analytics mua ON m.model_id = mua.model_id 
                    AND mua.created_at >= NOW() - INTERVAL '1 week'
                WHERE m.owner_user_id IS NOT NULL
                AND m.model_id NOT IN (
                    SELECT DISTINCT model_id 
                    FROM model_usage_analytics 
                    WHERE user_id = $1
                )
                GROUP BY m.model_id, m.name, m.short_description, m.long_description, m.created_at
                ORDER BY usage_count DESC, m.created_at DESC
                LIMIT 5
            """, user_id)
            
            return {
                'trending': [
                    {
                        'model_id': str(row['model_id']),
                        'name': row['name'],
                        'short_description': row['short_description'],
                        'long_description': row['long_description'],
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'usage_count': row['usage_count']
                    }
                    for row in trending
                ],
                'used': [
                    {
                        'model_id': str(row['model_id']),
                        'name': row['name'],
                        'short_description': row['short_description'],
                        'long_description': row['long_description'],
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'last_used': row['last_used'].isoformat() if row['last_used'] else None
                    }
                    for row in used
                ],
                'new': [
                    {
                        'model_id': str(row['model_id']),
                        'name': row['name'],
                        'short_description': row['short_description'],
                        'long_description': row['long_description'],
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None
                    }
                    for row in new
                ],
                'recommended': [
                    {
                        'model_id': str(row['model_id']),
                        'name': row['name'],
                        'short_description': row['short_description'],
                        'long_description': row['long_description'],
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'usage_count': row['usage_count']
                    }
                    for row in all_available
                ]
            }
    except Exception as e:
        print(f"Error getting model suggestions: {e}")
        raise HTTPException(status_code=500, detail="Failed to get model suggestions")

# --- Auth and static routes (unchanged) ---

@router.post("/signup")
async def signup(user: UserSignup, response: Response, pool=Depends(get_db_pool)):
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT user_id FROM users WHERE email = $1", user.email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already exists")

        hashed_pw = bcrypt.hashpw(user.password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

        await conn.execute(
            "INSERT INTO users (email, password_hash, name) VALUES ($1, $2, $3)",
            user.email,
            hashed_pw,
            user.name
        )

        record = await conn.fetchrow("SELECT user_id FROM users WHERE email = $1", user.email)
        user_id = record["user_id"]

        access_token, refresh_token_id, expires_at = await create_tokens(user_id, response)

        await conn.execute(
            "INSERT INTO refresh_tokens (token_id, user_id, expires_at) VALUES ($1, $2, $3)",
            refresh_token_id,
            user_id,
            expires_at,
        )

        return {"access_token": access_token, "message": "User created and logged in successfully"}

@router.post("/login")
async def login(user: UserLogin, response: Response, pool=Depends(get_db_pool)):
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            "SELECT user_id, password_hash FROM users WHERE email = $1", user.email
        )
        if not record or not bcrypt.checkpw(user.password.encode("utf-8"), record["password_hash"].encode("utf-8")):
            raise HTTPException(status_code=400, detail="Invalid email or password")
        user_id = record["user_id"]

        access_token, refresh_token_id, expires_at = await create_tokens(user_id, response)

        await conn.execute(
            "INSERT INTO refresh_tokens (token_id, user_id, expires_at) VALUES ($1, $2, $3)",
            refresh_token_id,
            user_id,
            expires_at,
        )

        return {"access_token": access_token, "message": "Login successful"}

@router.get("/auto-login")
async def auto_login(request: Request, pool=Depends(get_db_pool)):
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=401, detail="No refresh token")
    async with pool.acquire() as conn:
        record = await conn.fetchrow(
            "SELECT user_id FROM refresh_tokens WHERE token_id = $1 AND expires_at > now()", refresh_token
        )
        if not record:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        new_payload = {"sub": str(record["user_id"]), "exp": datetime.utcnow() + timedelta(minutes=15)}
        new_token = jwt.encode(new_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return {"access_token": new_token, "message": "Auto-login success"}

@router.post("/logout")
async def logout(request: Request, response: Response, pool=Depends(get_db_pool)):
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token:
        async with pool.acquire() as conn:
            await conn.execute("DELETE FROM refresh_tokens WHERE token_id = $1", refresh_token)
    response.delete_cookie("refresh_token")
    return {"message": "Logged out"}

@router.get("/hello")
async def hello(user_id: str = Depends(get_current_user_id), pool=Depends(get_db_pool)):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT name, email FROM users WHERE user_id = $1", user_id)
        if not row:
            raise HTTPException(status_code=404, detail="User not found")
    return {"message": f"Hello, {row['email']}; Your name is {row['name']}"}

@router.get("/l")
async def login_page():
    return FileResponse("static/login.html")

@router.get("/signup")
async def signup_page():
    return FileResponse("static/signup.html")

@router.get("/chats")
async def chats_page():
    return FileResponse("static/chat.html")

@router.get("/chat/{conversation_id}")
async def chat_page(conversation_id: str):
    return FileResponse("static/chat.html")

@router.get("/")
async def root():
    return FileResponse("static/login.html")