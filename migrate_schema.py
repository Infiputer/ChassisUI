#!/usr/bin/env python3
import os
"""
Migration script to update models table schema
"""

import asyncio
import asyncpg

async def migrate_schema():
    # Connect to database
    pool = await asyncpg.create_pool(
        os.environ.get("DATABASE_URL", "postgresql://chassis_user:@localhost/chassis_ui")
    )
    
    async with pool.acquire() as conn:
        print("Starting schema migration...")
        
        # Check if the new columns already exist
        columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'models' AND table_schema = 'public'
        """)
        
        column_names = [col['column_name'] for col in columns]
        print(f"Current columns: {column_names}")
        
        # Add new columns if they don't exist
        if 'short_description' not in column_names:
            print("Adding short_description column...")
            await conn.execute("""
                ALTER TABLE models ADD COLUMN short_description TEXT
            """)
        
        if 'long_description' not in column_names:
            print("Adding long_description column...")
            await conn.execute("""
                ALTER TABLE models ADD COLUMN long_description TEXT
            """)
        
        # Migrate existing data
        print("Migrating existing data...")
        if 'description' in column_names:
            await conn.execute("""
                UPDATE models 
                SET short_description = description 
                WHERE short_description IS NULL AND description IS NOT NULL
            """)
            print("Migrated description to short_description")
        
        print("Schema migration completed successfully!")
        
        # Verify the new schema
        new_columns = await conn.fetch("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'models' AND table_schema = 'public'
            ORDER BY ordinal_position
        """)
        
        print(f"Final columns: {[col['column_name'] for col in new_columns]}")
        
        # Show sample data
        sample_data = await conn.fetch("""
            SELECT model_id, name, short_description, long_description 
            FROM models 
            LIMIT 3
        """)
        
        print("\nSample data:")
        for row in sample_data:
            print(f"  {row['name']}: {row['short_description']}")

if __name__ == "__main__":
    asyncio.run(migrate_schema()) 