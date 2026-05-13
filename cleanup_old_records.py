"""
Cleanup Script for Try-On Records
Automatically deletes records older than 24 hours
"""

import os
import schedule
import time
import psycopg2
from datetime import datetime, timedelta

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


# -------------------------------
# Cleanup Function
# -------------------------------
def cleanup_old_records():
    """Delete try-on records older than 24 hours"""

    conn = None
    cursor = None

    try:
        # Connect to database
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Calculate the cutoff time (24 hours ago)
        cutoff_time = datetime.utcnow() - timedelta(hours=24)

        # Count records before deletion
        cursor.execute("""
            SELECT COUNT(*) 
            FROM try_on_record 
            WHERE created_at < %s
        """, (cutoff_time,))

        count = cursor.fetchone()[0]

        if count > 0:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Found {count} records older than 24 hours")

            # Delete the records
            cursor.execute("""
                DELETE FROM try_on_record 
                WHERE created_at < %s
            """, (cutoff_time,))

            conn.commit()
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Successfully deleted {count} old records")
        else:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] No records older than 24 hours found")

    except psycopg2.Error as e:
        if conn:
            conn.rollback()
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ERROR: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# -------------------------------
# Get Statistics
# -------------------------------
def get_database_stats():
    """Display current database statistics"""

    conn = None
    cursor = None

    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        # Total records
        cursor.execute("SELECT COUNT(*) FROM try_on_record")
        total = cursor.fetchone()[0]

        # Records older than 24 hours
        cutoff_time = datetime.utcnow() - timedelta(hours=24)
        cursor.execute("SELECT COUNT(*) FROM try_on_record WHERE created_at < %s", (cutoff_time,))
        old = cursor.fetchone()[0]

        # Records from last 24 hours
        recent = total - old

        print("\n" + "=" * 60)
        print("DATABASE STATISTICS")
        print("=" * 60)
        print(f"Total records:                {total}")
        print(f"Records < 24 hours old:       {recent}")
        print(f"Records > 24 hours old:       {old}")
        print("=" * 60 + "\n")

    except psycopg2.Error as e:
        print(f"Error getting stats: {str(e)}")

    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# -------------------------------
# Manual Cleanup (Run Once)
# -------------------------------
def run_manual_cleanup():
    """Run cleanup once manually"""
    print("=" * 60)
    print("MANUAL CLEANUP - Deleting records older than 24 hours")
    print("=" * 60)

    get_database_stats()
    cleanup_old_records()

    print("\n" + "=" * 60)
    print("Cleanup completed")
    print("=" * 60)


# -------------------------------
# Scheduled Cleanup (Run Every Hour)
# -------------------------------
def run_scheduled_cleanup():
    """Schedule cleanup to run every hour"""
    print("=" * 60)
    print("SCHEDULED CLEANUP SERVICE")
    print("Cleanup runs every hour")
    print("Press Ctrl+C to stop")
    print("=" * 60)

    # Schedule the cleanup to run every hour
    schedule.every(1).hours.do(cleanup_old_records)

    # Run immediately on startup
    get_database_stats()
    cleanup_old_records()

    # Keep the script running
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        print("\n" + "=" * 60)
        print("Cleanup service stopped by user")
        print("=" * 60)


# -------------------------------
# Main Execution
# -------------------------------
if __name__ == "__main__":
    import sys

    print("\n" + "=" * 60)
    print("TRY-ON RECORD CLEANUP SCRIPT")
    print("=" * 60)

    # Check if database has required columns
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'try_on_record' 
            AND column_name = 'created_at'
        """)

        if cursor.fetchone() is None:
            print("\n❌ ERROR: The 'created_at' column does not exist!")
            print("\nPlease run the migration script first:")
            print("  python migrate_database.py")
            cursor.close()
            conn.close()
            sys.exit(1)

        cursor.close()
        conn.close()

    except psycopg2.Error as e:
        print(f"\n❌ Database connection error: {str(e)}")
        sys.exit(1)

    # Run cleanup based on arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--manual":
            run_manual_cleanup()
        elif sys.argv[1] == "--stats":
            get_database_stats()
        else:
            print("\nUsage:")
            print("  python cleanup_old_records.py          # Run as scheduled service")
            print("  python cleanup_old_records.py --manual # Run once and exit")
            print("  python cleanup_old_records.py --stats  # Show statistics only")
    else:
        # Run as a continuous service
        run_scheduled_cleanup()