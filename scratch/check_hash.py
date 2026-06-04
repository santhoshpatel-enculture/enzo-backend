import bcrypt

hash_val = "$2b$10$t00hGxmj0Q9XchcBJAG4mObBygucBPOJ/Ou5Ykqhz3nwCY1dH3gZu"
passwords = ["Enzo@2024", "password", "enculture", "123456", "admin", "Admin@123", "admin123", "password123"]

for p in passwords:
    try:
        match = bcrypt.checkpw(p.encode(), hash_val.encode())
        print(f"Password '{p}': {'MATCH' if match else 'NO MATCH'}")
    except Exception as e:
        print(f"Error checking '{p}': {e}")
