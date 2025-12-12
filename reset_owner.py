#!/usr/bin/env python3
"""
CLI tool to reset the primary owner's password.
Use this when you've lost access to the primary owner account
and cannot use the password reset email flow.

Usage:
    python reset_owner.py <new_password>
"""
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db


def main():
    if len(sys.argv) != 2:
        print("Usage: python reset_owner.py <new_password>")
        print("")
        print("Resets the primary owner's password.")
        print("The primary owner is the first admin account created (lowest ID).")
        sys.exit(1)
    
    new_password = sys.argv[1]
    
    if len(new_password) < 6:
        print("Error: Password must be at least 6 characters long.")
        sys.exit(1)
    
    # Initialize database (in case it's not already)
    db.init_db()
    
    # Get the primary owner
    first_admin = db.get_first_admin()
    
    if not first_admin:
        print("Error: No admin accounts found.")
        print("Create an admin through the web interface first.")
        sys.exit(1)
    
    if first_admin['role'] != 'owner':
        print(f"Warning: First admin '{first_admin['username']}' is not an owner (role: {first_admin['role']}).")
        print("Updating password anyway...")
    
    # Update the password
    db.update_admin_password(first_admin['id'], new_password)
    
    print("-------------------------------------------")
    print("       PASSWORD RESET SUCCESSFUL")
    print("-------------------------------------------")
    print("")
    print(f"  Account:  {first_admin['username']}")
    print(f"  Role:     {first_admin['role']}")
    print("")
    print("You can now login with the new password.")
    print("-------------------------------------------")


if __name__ == '__main__':
    main()
