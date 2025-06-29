#!/usr/bin/env python3
"""
Test script to demonstrate the efficiency of shared streaming vs multiple model calls
"""

import asyncio
import time
import json
from typing import List, Dict

class MockModelEndpoint:
    """Mock model endpoint to simulate the inefficiency of multiple calls"""
    
    def __init__(self):
        self.call_count = 0
        self.tokens_generated = []
    
    async def generate_response(self, messages: List[Dict], call_id: str) -> List[str]:
        """Simulate model response generation"""
        self.call_count += 1
        print(f"🔴 MODEL CALL #{self.call_count} ({call_id}) - Processing {len(messages)} messages")
        
        # Simulate token generation
        response = f"This is response from call #{self.call_count}. "
        response += "The model is processing the same conversation context again, which is inefficient. "
        response += "In a real scenario, this would consume additional compute resources and time. "
        response += "The shared streaming approach eliminates this redundancy by reusing the same model connection."
        
        tokens = response.split()
        self.tokens_generated.extend(tokens)
        
        # Simulate streaming delay
        await asyncio.sleep(0.1)
        
        print(f"   Generated {len(tokens)} tokens")
        return tokens

class SharedStreamManager:
    """Efficient shared streaming manager"""
    
    def __init__(self):
        self.active_streams: Dict[str, 'SharedStream'] = {}
        self.total_model_calls = 0
    
    def get_or_create_stream(self, conversation_id: str, messages: List[Dict]) -> 'SharedStream':
        """Get existing stream or create new one"""
        if conversation_id in self.active_streams:
            stream = self.active_streams[conversation_id]
            if stream.is_active():
                print(f"🟢 REUSING existing stream for conversation {conversation_id}")
                return stream
            else:
                del self.active_streams[conversation_id]
        
        # Create new shared stream
        self.total_model_calls += 1
        stream = SharedStream(conversation_id, messages, self.total_model_calls)
        self.active_streams[conversation_id] = stream
        print(f"🟢 CREATED new shared stream for conversation {conversation_id} (call #{self.total_model_calls})")
        return stream

class SharedStream:
    """Shared stream that distributes tokens to multiple consumers"""
    
    def __init__(self, conversation_id: str, messages: List[Dict], call_number: int):
        self.conversation_id = conversation_id
        self.messages = messages
        self.call_number = call_number
        self.consumers = []
        self.tokens = []
        self.is_complete = False
        self.is_active = True
    
    async def start_streaming(self):
        """Start the actual model streaming"""
        print(f"   📡 Starting model streaming for call #{self.call_number}")
        
        # Simulate token generation
        response = f"This is response from shared call #{self.call_number}. "
        response += "The model processes the conversation context only once. "
        response += "Multiple consumers can subscribe to the same stream. "
        response += "This eliminates redundant model calls and improves efficiency."
        
        tokens = response.split()
        self.tokens = tokens
        
        # Distribute tokens to all consumers
        for consumer in self.consumers:
            await consumer.receive_tokens(tokens)
        
        self.is_complete = True
        print(f"   ✅ Streaming completed for call #{self.call_number}")
    
    def add_consumer(self, consumer):
        """Add a consumer to this stream"""
        self.consumers.append(consumer)
        print(f"   👥 Added consumer {consumer.name} to shared stream")
    
    def remove_consumer(self, consumer):
        """Remove a consumer from this stream"""
        if consumer in self.consumers:
            self.consumers.remove(consumer)
            print(f"   👥 Removed consumer {consumer.name} from shared stream")

class StreamConsumer:
    """Base consumer class"""
    
    def __init__(self, name: str, stream: SharedStream):
        self.name = name
        self.stream = stream
        self.received_tokens = []
    
    async def receive_tokens(self, tokens: List[str]):
        """Receive tokens from the shared stream"""
        self.received_tokens.extend(tokens)
        print(f"   📨 {self.name} received {len(tokens)} tokens")

async def test_inefficient_approach():
    """Test the old inefficient approach with multiple model calls"""
    print("\n" + "="*60)
    print("🔴 TESTING INEFFICIENT APPROACH (Multiple Model Calls)")
    print("="*60)
    
    model = MockModelEndpoint()
    messages = [{"role": "user", "content": "Hello, how are you?"}]
    
    start_time = time.time()
    
    # Original streaming call
    print("\n1. Original streaming call:")
    tokens1 = await model.generate_response(messages, "original")
    
    # Background task call (SAME MESSAGES!)
    print("\n2. Background task call:")
    tokens2 = await model.generate_response(messages, "background")
    
    # Resume streaming call (SAME MESSAGES AGAIN!)
    print("\n3. Resume streaming call:")
    tokens3 = await model.generate_response(messages, "resume")
    
    end_time = time.time()
    
    print(f"\n📊 RESULTS:")
    print(f"   Total model calls: {model.call_count}")
    print(f"   Total tokens generated: {len(model.tokens_generated)}")
    print(f"   Time taken: {end_time - start_time:.2f} seconds")
    print(f"   Efficiency: POOR - Same context processed 3 times!")

async def test_efficient_approach():
    """Test the new efficient approach with shared streaming"""
    print("\n" + "="*60)
    print("🟢 TESTING EFFICIENT APPROACH (Shared Streaming)")
    print("="*60)
    
    manager = SharedStreamManager()
    messages = [{"role": "user", "content": "Hello, how are you?"}]
    conversation_id = "test-conversation"
    
    start_time = time.time()
    
    # Get or create shared stream
    shared_stream = manager.get_or_create_stream(conversation_id, messages)
    
    # Create consumers
    frontend_consumer = StreamConsumer("Frontend", shared_stream)
    background_consumer = StreamConsumer("Background", shared_stream)
    resume_consumer = StreamConsumer("Resume", shared_stream)
    
    # Add consumers to stream
    shared_stream.add_consumer(frontend_consumer)
    shared_stream.add_consumer(background_consumer)
    shared_stream.add_consumer(resume_consumer)
    
    # Start streaming (only ONE model call!)
    await shared_stream.start_streaming()
    
    end_time = time.time()
    
    print(f"\n📊 RESULTS:")
    print(f"   Total model calls: {manager.total_model_calls}")
    print(f"   Total tokens generated: {len(shared_stream.tokens)}")
    print(f"   Time taken: {end_time - start_time:.2f} seconds")
    print(f"   Efficiency: EXCELLENT - Context processed only once!")
    
    print(f"\n📨 Consumer Results:")
    print(f"   Frontend received: {len(frontend_consumer.received_tokens)} tokens")
    print(f"   Background received: {len(background_consumer.received_tokens)} tokens")
    print(f"   Resume received: {len(resume_consumer.received_tokens)} tokens")

async def main():
    """Run both tests to compare efficiency"""
    print("🚀 COMPARING STREAMING APPROACHES")
    print("This test demonstrates the efficiency improvement of shared streaming")
    
    await test_inefficient_approach()
    await test_efficient_approach()
    
    print("\n" + "="*60)
    print("🎯 SUMMARY")
    print("="*60)
    print("The shared streaming approach eliminates redundant model calls by:")
    print("✅ Reusing the same model connection across all consumers")
    print("✅ Processing the conversation context only once")
    print("✅ Distributing tokens to multiple consumers efficiently")
    print("✅ Reducing compute costs and improving response times")
    print("✅ Eliminating the inefficiency of reprompting the AI multiple times")

if __name__ == "__main__":
    asyncio.run(main()) 