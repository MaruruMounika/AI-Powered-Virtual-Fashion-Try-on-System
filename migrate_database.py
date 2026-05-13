"""
Database Migration Script
This script adds the missing columns to the try_on_record table
Run this BEFORE running the cleanup script
"""

import psycopg2
from datetime import datetime

# -------------------------------
# Database Configuration
# -------------------------------
DB_CONFIG = {
    'dbname': 'postgres',
    'user': 'postgres',
    'password': '12345',
    'host': 'localhost',
    'port': '5432'
}


def run_migration():
    """Add user_id and created_at columns to try_on_record table"""

    conn = None
    cursor = None

    try:
        # Connect to database
        print("Connecting to database...")
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        print("\n" + "=" * 60)
        print("DATABASE MIGRATION - Adding columns to try_on_record")
        print("=" * 60)

        # Check if user table exists, create if not
        print("\n1. Checking if 'user' table exists...")
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'user'
            );
        """)
        user_table_exists = cursor.fetchone()[0]

        if not user_table_exists:
            print("   Creating 'user' table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS public.user
                (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(120) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            print("   ✓ User table created")
        else:
            print("   ✓ User table already exists")

        # Check if created_at column exists
        print("\n2. Checking if 'created_at' column exists...")
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'try_on_record' 
            AND column_name = 'created_at';
        """)
        created_at_exists = cursor.fetchone() is not None

        if not created_at_exists:
            print("   Adding 'created_at' column...")
            cursor.execute("""
                ALTER TABLE public.try_on_record 
                ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
            """)
            print("   ✓ created_at column added")

            # Update existing records with current timestamp
            print("   Updating existing records with current timestamp...")
            cursor.execute("""
                UPDATE public.try_on_record 
                SET created_at = CURRENT_TIMESTAMP 
                WHERE created_at IS NULL;
            """)
            print("   ✓ Existing records updated")
        else:
            print("   ✓ created_at column already exists")

        # Check if user_id column exists
        print("\n3. Checking if 'user_id' column exists...")
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'try_on_record' 
            AND column_name = 'user_id';
        """)
        user_id_exists = cursor.fetchone() is not None

        if not user_id_exists:
            print("   Adding 'user_id' column...")
            cursor.execute("""
                ALTER TABLE public.try_on_record 
                ADD COLUMN user_id INTEGER;
            """)
            print("   ✓ user_id column added")

            # Add foreign key constraint
            print("   Adding foreign key constraint...")
            cursor.execute("""
                ALTER TABLE public.try_on_record 
                ADD CONSTRAINT try_on_record_user_id_fkey 
                FOREIGN KEY (user_id) REFERENCES public.user(id) ON DELETE CASCADE;
            """)
            print("   ✓ Foreign key constraint added")
        else:
            print("   ✓ user_id column already exists")

        # Commit all changes
        conn.commit()

        print("\n" + "=" * 60)
        print("✓ MIGRATION COMPLETED SUCCESSFULLY")
        print("=" * 60)

        # Display current schema
        print("\nCurrent try_on_record table schema:")
        cursor.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns 
            WHERE table_name = 'try_on_record'
            ORDER BY ordinal_position;
        """)

        columns = cursor.fetchall()
        print("-" * 60)
        print(f"{'Column Name':<20} {'Data Type':<20} {'Nullable':<10}")
        print("-" * 60)
        for col in columns:
            print(f"{col[0]:<20} {col[1]:<20} {col[2]:<10}")
        print("-" * 60)

    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        print(f"\n❌ ERROR: {str(e)}")
        print("Migration failed. No changes were made.")
        return False

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        print("\nDatabase connection closed.")

    return True


def verify_migration():
    """Verify that the migration was successful"""

    conn = None
    cursor = None

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Check columns
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'try_on_record'
            AND column_name IN ('user_id', 'created_at');
        """)

        columns = [row[0] for row in cursor.fetchall()]

        print("\n" + "=" * 60)
        print("VERIFICATION")
        print("=" * 60)

        if 'created_at' in columns:
            print("✓ created_at column exists")
        else:
            print("✗ created_at column missing")

        if 'user_id' in columns:
            print("✓ user_id column exists")
        else:
            print("✗ user_id column missing")

        print("=" * 60)

    except psycopg2.Error as e:
        print(f"Verification error: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# -------------------------------
# Main Execution
# -------------------------------
if __name__ == "__main__":
    import sys

    print("\n" + "=" * 60)
    print("TRY-ON RECORD DATABASE MIGRATION")
    print("=" * 60)
    print("\nThis script will add the following columns:")
    print("  - user_id (INTEGER, Foreign Key to user.id)")
    print("  - created_at (TIMESTAMP, Default: CURRENT_TIMESTAMP)")
    print("\n" + "=" * 60)

    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        verify_migration()
    else:
        response = input("\nProceed with migration? (yes/no): ")

        if response.lower() in ['yes', 'y']:
            success = run_migration()
            if success:
                verify_migration()
        else:
            print("\nMigration cancelled.")